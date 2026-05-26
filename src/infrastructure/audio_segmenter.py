import os
import traceback
from ctypes import c_float, c_short, POINTER, c_void_p, c_ulong
from typing import List, Optional

from src.infrastructure.subtitle_parser import SubtitleLine
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class AudioSegmenter:
    SILENCE_THRESHOLD_DEFAULT = 3000
    MIN_SILENCE_MS_DEFAULT = 300
    MIN_SEGMENT_MS_DEFAULT = 800
    SCAN_STEP_MS = 30

    BASS_DATA_FLOAT = 0x40000000
    BASS_DATA_AVAILABLE = 0
    BASS_LEVEL_RMS = 0x10
    BASS_LEVEL_MONO = 0x100

    @staticmethod
    def detect_segments(
        audio_path: str,
        silence_threshold: int = SILENCE_THRESHOLD_DEFAULT,
        min_silence_ms: int = MIN_SILENCE_MS_DEFAULT,
        min_segment_ms: int = MIN_SEGMENT_MS_DEFAULT,
        progress_callback=None,
    ) -> Optional[List[SubtitleLine]]:
        from src.infrastructure.bass_engine import BASSEngine

        engine = BASSEngine()
        if not engine._initialized_flag:
            logger.error("[SEG-DIAG] BASS not initialized, cannot detect segments")
            return None

        logger.info(f"[SEG-DIAG] === Starting segmentation ===")
        logger.info(f"[SEG-DIAG] File: {audio_path}")
        logger.info(f"[SEG-DIAG] File exists: {os.path.exists(audio_path)}, size: {os.path.getsize(audio_path) if os.path.exists(audio_path) else 'N/A'}")
        logger.info(f"[SEG-DIAG] Params: threshold={silence_threshold}, min_silence={min_silence_ms}, min_segment={min_segment_ms}")

        decode_stream = engine.load_decode(audio_path)
        if decode_stream == 0:
            err = engine._bass.BASS_ErrorGetCode()
            logger.warning(f"[SEG-DIAG] First load_decode failed, BASS error={err}, releasing playback stream and retrying")
            engine.unload()
            import time as _time
            _time.sleep(0.2)
            decode_stream = engine.load_decode(audio_path)
            if decode_stream == 0:
                err2 = engine._bass.BASS_ErrorGetCode()
                logger.error(f"[SEG-DIAG] Second load_decode also failed, BASS error={err2}")
                return None

        logger.info(f"[SEG-DIAG] Decode stream created: handle={decode_stream}")

        try:
            len_bytes = engine._bass.BASS_ChannelGetLength(decode_stream, engine.BASS_POS_BYTE)
            duration_sec = engine._bass.BASS_ChannelBytes2Seconds(decode_stream, len_bytes)
            duration_ms = int(duration_sec * 1000)
            logger.info(f"[SEG-DIAG] len_bytes={len_bytes}, duration_sec={duration_sec}, duration_ms={duration_ms}")

            if duration_ms <= 0:
                logger.error(f"[SEG-DIAG] Invalid duration, aborting")
                return None

            available = engine._bass.BASS_ChannelGetData(decode_stream, None, AudioSegmenter.BASS_DATA_AVAILABLE)
            logger.info(f"[SEG-DIAG] BASS_DATA_AVAILABLE (buffered bytes)={available}")

            levels = AudioSegmenter._scan_with_getlevelex(engine, decode_stream, duration_ms, progress_callback)

            if not levels or max(l[1] for l in levels) == 0:
                logger.info("[SEG-DIAG] GetLevelEx produced no useful data, trying GetLevel fallback")
                engine.free_stream(decode_stream)
                decode_stream = engine.load_decode(audio_path)
                if decode_stream != 0:
                    levels_fb = AudioSegmenter._scan_with_getlevel(engine, decode_stream, duration_ms, progress_callback)
                    if levels_fb and max(l[1] for l in levels_fb) > 0:
                        levels = levels_fb
                        logger.info(f"[SEG-DIAG] GetLevel fallback succeeded: {len(levels)} chunks")
                    else:
                        logger.info("[SEG-DIAG] GetLevel fallback also failed, trying GetData raw PCM fallback")
                        engine.free_stream(decode_stream)
                        decode_stream = engine.load_decode(audio_path)
                        if decode_stream != 0:
                            levels_fb2 = AudioSegmenter._scan_with_getdata_raw(engine, decode_stream, duration_ms, progress_callback)
                            if levels_fb2 and max(l[1] for l in levels_fb2) > 0:
                                levels = levels_fb2
                                logger.info(f"[SEG-DIAG] GetData raw PCM fallback succeeded: {len(levels)} chunks")

            if not levels:
                logger.error("[SEG-DIAG] All scan methods failed, no levels collected")
                return None

            max_level = max(l[1] for l in levels)
            avg_level = sum(l[1] for l in levels) / len(levels)
            non_zero = sum(1 for l in levels if l[1] > 0)
            logger.info(f"[SEG-DIAG] Final level stats: count={len(levels)}, max={max_level}, avg={avg_level:.1f}, non_zero={non_zero}")

            if max_level == 0:
                logger.error("[SEG-DIAG] All levels are 0 even after all fallbacks")
                return None

            segments = AudioSegmenter._build_segments_adaptive(
                levels, duration_ms, silence_threshold, min_silence_ms, min_segment_ms
            )

            logger.info(f"[SEG-DIAG] Result: {len(segments)} segments from {duration_ms}ms audio")
            return segments

        except Exception as e:
            logger.error(f"[SEG-DIAG] Exception: {e}")
            logger.error(traceback.format_exc())
            return None
        finally:
            engine.free_stream(decode_stream)

    @staticmethod
    def _scan_with_getlevelex(engine, decode_stream, duration_ms, progress_callback):
        logger.info("[SEG-DIAG] --- Method 1: BASS_ChannelGetLevelEx ---")
        levels = []
        step_sec = AudioSegmenter.SCAN_STEP_MS / 1000.0
        total_steps = max(duration_ms // AudioSegmenter.SCAN_STEP_MS, 1)
        error_count = 0
        step = 0

        try:
            engine._bass.BASS_ChannelGetLevelEx.restype = bool
            from ctypes import c_float as cf, POINTER as POI, c_ulong as cul, c_float as cfl
            engine._bass.BASS_ChannelGetLevelEx.argtypes = [cul, POI(cf), cfl, cul]
        except Exception as e:
            logger.warning(f"[SEG-DIAG] Cannot setup GetLevelEx prototype: {e}")
            return levels

        while True:
            pos_bytes = engine._bass.BASS_ChannelGetPosition(decode_stream, engine.BASS_POS_BYTE)
            pos_ms = int(engine._bass.BASS_ChannelBytes2Seconds(decode_stream, pos_bytes) * 1000)

            if pos_ms >= duration_ms:
                break

            try:
                buf = (c_float * 2)()
                result = engine._bass.BASS_ChannelGetLevelEx(
                    decode_stream, buf, step_sec,
                    AudioSegmenter.BASS_LEVEL_RMS | AudioSegmenter.BASS_LEVEL_MONO
                )
                if step < 5 or step % 500 == 0:
                    logger.info(f"[SEG-DIAG] GetLevelEx step={step}, pos={pos_ms}ms, result={result}, buf=[{buf[0]:.6f}, {buf[1]:.6f}]")

                if result:
                    rms_val = buf[0]
                    level = int(rms_val * 32768)
                    levels.append((pos_ms, level))
                else:
                    error_count += 1
                    err_code = engine._bass.BASS_ErrorGetCode()
                    if error_count <= 5:
                        logger.warning(f"[SEG-DIAG] GetLevelEx returned False at pos={pos_ms}ms, BASS error={err_code}")
                    if error_count >= 10:
                        logger.error(f"[SEG-DIAG] Too many GetLevelEx errors ({error_count}), stopping")
                        break
            except Exception as e:
                error_count += 1
                if error_count <= 3:
                    logger.warning(f"[SEG-DIAG] GetLevelEx exception at pos={pos_ms}ms: {e}")
                if error_count >= 5:
                    break

            if progress_callback and step % 50 == 0:
                progress_callback(int(step / total_steps * 100))
            step += 1

        logger.info(f"[SEG-DIAG] GetLevelEx scan: {len(levels)} levels, {error_count} errors")
        return levels

    @staticmethod
    def _scan_with_getlevel(engine, decode_stream, duration_ms, progress_callback):
        logger.info("[SEG-DIAG] --- Method 2: BASS_ChannelGetLevel ---")
        levels = []
        step_ms = AudioSegmenter.SCAN_STEP_MS
        total_steps = max(duration_ms // step_ms, 1)
        error_count = 0
        step = 0

        engine._bass.BASS_ChannelGetLevel.restype = c_ulong
        engine._bass.BASS_ChannelGetLevel.argtypes = [c_ulong]

        while True:
            pos_bytes = engine._bass.BASS_ChannelGetPosition(decode_stream, engine.BASS_POS_BYTE)
            pos_ms = int(engine._bass.BASS_ChannelBytes2Seconds(decode_stream, pos_bytes) * 1000)

            if pos_ms >= duration_ms:
                break

            level_dword = engine._bass.BASS_ChannelGetLevel(decode_stream)
            err_code = engine._bass.BASS_ErrorGetCode()

            if level_dword == 0 and err_code != 0:
                error_count += 1
                if error_count <= 5:
                    logger.warning(f"[SEG-DIAG] GetLevel returned 0 at pos={pos_ms}ms, BASS error={err_code}")
                if error_count >= 10:
                    break
                continue

            left = (level_dword >> 16) & 0xFFFF
            right = level_dword & 0xFFFF
            peak = max(left, right)

            if step < 5 or step % 500 == 0:
                logger.info(f"[SEG-DIAG] GetLevel step={step}, pos={pos_ms}ms, raw=0x{level_dword:08X}, L={left}, R={right}, peak={peak}")

            levels.append((pos_ms, peak))

            if progress_callback and step % 50 == 0:
                progress_callback(int(step / total_steps * 100))
            step += 1

            if pos_ms >= duration_ms - step_ms:
                break

        logger.info(f"[SEG-DIAG] GetLevel scan: {len(levels)} levels, {error_count} errors")
        return levels

    @staticmethod
    def _scan_with_getdata_raw(engine, decode_stream, duration_ms, progress_callback):
        logger.info("[SEG-DIAG] --- Method 3: BASS_ChannelGetData (raw 16-bit PCM) ---")
        levels = []
        step_ms = AudioSegmenter.SCAN_STEP_MS
        total_steps = max(duration_ms // step_ms, 1)

        len_bytes = engine._bass.BASS_ChannelGetLength(decode_stream, engine.BASS_POS_BYTE)
        bytes_per_ms = len_bytes / max(duration_ms, 1)
        chunk_bytes = int(bytes_per_ms * step_ms)
        chunk_bytes = max(chunk_bytes, 1024)
        chunk_bytes = (chunk_bytes // 2) * 2

        buf_shorts = chunk_bytes // 2
        buf = (c_short * buf_shorts)()

        engine._bass.BASS_ChannelGetData.restype = c_ulong
        engine._bass.BASS_ChannelGetData.argtypes = [c_ulong, c_void_p, c_ulong]

        step = 0
        error_count = 0

        while True:
            pos_bytes = engine._bass.BASS_ChannelGetPosition(decode_stream, engine.BASS_POS_BYTE)
            pos_ms = int(engine._bass.BASS_ChannelBytes2Seconds(decode_stream, pos_bytes) * 1000)

            if pos_ms >= duration_ms:
                break

            got = engine._bass.BASS_ChannelGetData(decode_stream, buf, chunk_bytes)

            if got == 0:
                break

            if got >= 0x80000000:
                error_count += 1
                err_code = engine._bass.BASS_ErrorGetCode()
                if error_count <= 3:
                    logger.warning(f"[SEG-DIAG] GetData error at {pos_ms}ms, got=0x{got:08X}, BASS error={err_code}")
                if error_count >= 5:
                    break
                continue

            sample_count = got // 2
            peak = 0
            for i in range(min(sample_count, buf_shorts)):
                val = abs(buf[i])
                if val > peak:
                    peak = val

            if step < 5 or step % 500 == 0:
                logger.info(f"[SEG-DIAG] GetData step={step}, pos={pos_ms}ms, got={got}, samples={sample_count}, peak={peak}")

            levels.append((pos_ms, peak))

            if progress_callback and step % 50 == 0:
                progress_callback(int(step / total_steps * 100))
            step += 1

            if got < chunk_bytes:
                break

        logger.info(f"[SEG-DIAG] GetData raw scan: {len(levels)} levels, {error_count} errors")
        return levels

    @staticmethod
    def _build_segments_adaptive(
        levels: list,
        duration_ms: int,
        user_threshold: int,
        min_silence_ms: int,
        min_segment_ms: int,
    ) -> List[SubtitleLine]:
        if not levels:
            return []

        energies = [l[1] for l in levels]

        sorted_energies = sorted(energies)
        n = len(sorted_energies)
        p10 = sorted_energies[int(n * 0.10)]
        p25 = sorted_energies[int(n * 0.25)]
        p50 = sorted_energies[int(n * 0.50)]
        p75 = sorted_energies[int(n * 0.75)]
        p90 = sorted_energies[int(n * 0.90)]
        max_e = sorted_energies[-1]

        logger.info(
            f"[SEG-DIAG] Energy distribution: p10={p10}, p25={p25}, p50={p50}, "
            f"p75={p75}, p90={p90}, max={max_e}"
        )

        if user_threshold > 0:
            threshold = user_threshold
            logger.info(f"[SEG-DIAG] Using user-specified threshold: {threshold}")
        else:
            noise_floor = p25
            speech_level = p75
            if speech_level <= noise_floor:
                speech_level = p90
            if speech_level <= noise_floor:
                threshold = max_e // 4
            else:
                dynamic_range = speech_level - noise_floor
                threshold = noise_floor + int(dynamic_range * 0.25)
            threshold = max(threshold, 50)
            logger.info(
                f"[SEG-DIAG] Adaptive threshold: noise_floor={noise_floor}, speech_level={speech_level}, "
                f"threshold={threshold}"
            )

        smoothed = AudioSegmenter._smooth_energy(energies, window=5)

        is_low = [e < threshold for e in smoothed]

        low_runs = []
        in_low = False
        run_start = 0

        for i, low in enumerate(is_low):
            if low and not in_low:
                in_low = True
                run_start = i
            elif not low and in_low:
                in_low = False
                run_end = i - 1
                run_duration = levels[run_end][0] - levels[run_start][0]
                if run_duration >= min_silence_ms:
                    low_runs.append((run_start, run_end))
        if in_low:
            run_end = len(is_low) - 1
            run_duration = levels[run_end][0] - levels[run_start][0]
            if run_duration >= min_silence_ms:
                low_runs.append((run_start, run_end))

        if not low_runs:
            logger.info("[SEG-DIAG] No pause segments found with current threshold, trying lower threshold")
            fallback_threshold = max(p10, 30)
            is_low_fb = [e < fallback_threshold for e in smoothed]

            in_low = False
            for i, low in enumerate(is_low_fb):
                if low and not in_low:
                    in_low = True
                    run_start = i
                elif not low and in_low:
                    in_low = False
                    run_end = i - 1
                    run_duration = levels[run_end][0] - levels[run_start][0]
                    if run_duration >= min_silence_ms:
                        low_runs.append((run_start, run_end))
            if in_low:
                run_end = len(is_low_fb) - 1
                run_duration = levels[run_end][0] - levels[run_start][0]
                if run_duration >= min_silence_ms:
                    low_runs.append((run_start, run_end))

            if low_runs:
                logger.info(f"[SEG-DIAG] Fallback threshold={fallback_threshold} found {len(low_runs)} pauses")
            else:
                logger.info("[SEG-DIAG] Still no pauses found, returning single segment")

        cut_points = []
        for run_start_idx, run_end_idx in low_runs:
            start_energy = smoothed[run_start_idx]
            end_energy = smoothed[run_end_idx]
            if start_energy <= end_energy:
                cut_ms = levels[run_start_idx][0]
            else:
                cut_ms = levels[run_end_idx][0]
            cut_points.append(cut_ms)

        segments = []
        if not cut_points:
            if duration_ms >= min_segment_ms:
                segments.append(
                    SubtitleLine(index=0, start_ms=0, end_ms=duration_ms, text="(auto)")
                )
            return segments

        prev_end = 0
        idx = 0
        for cut_ms in cut_points:
            if cut_ms - prev_end >= min_segment_ms:
                segments.append(
                    SubtitleLine(
                        index=idx, start_ms=prev_end, end_ms=cut_ms,
                        text=f"(auto {idx + 1})"
                    )
                )
                idx += 1
            prev_end = cut_ms

        if duration_ms - prev_end >= min_segment_ms:
            segments.append(
                SubtitleLine(
                    index=idx, start_ms=prev_end, end_ms=duration_ms,
                    text=f"(auto {idx + 1})"
                )
            )

        for i in range(len(segments)):
            segments[i].index = i

        logger.info(
            f"[SEG-DIAG] Segmentation result: {len(segments)} segments, "
            f"threshold={threshold}, min_silence={min_silence_ms}ms, min_segment={min_segment_ms}ms"
        )
        return segments

    @staticmethod
    def _smooth_energy(energies: list, window: int = 5) -> list:
        if not energies or window <= 1:
            return list(energies)

        smoothed = []
        half = window // 2
        n = len(energies)
        for i in range(n):
            start = max(0, i - half)
            end = min(n, i + half + 1)
            avg = sum(energies[start:end]) / (end - start)
            smoothed.append(avg)
        return smoothed
