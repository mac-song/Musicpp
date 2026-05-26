import json
import os
import uuid
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, List, Optional

from src.core.database_service import DatabaseService
from src.infrastructure.media_extractor import ExtractOptions, MediaExtractor
from src.infrastructure.subtitle_parser import Chapter, SubtitleLine, SubtitleParser
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class StudyMaterial:
    id: str
    title: str
    source: str
    source_url: str
    audio_path: str
    subtitle_path: str
    subtitle_path_secondary: str
    chapters_json: str
    duration_ms: int
    created_at: str
    last_played_at: str
    progress_ms: int

    def get_chapters(self) -> List[Chapter]:
        if not self.chapters_json or self.chapters_json == "[]":
            return []
        try:
            raw = json.loads(self.chapters_json)
            return [Chapter(**ch) for ch in raw]
        except Exception:
            return []


class StudyManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._db = DatabaseService()
        self._extractor = MediaExtractor()
        self._initialized = True

    def get_materials_dir(self) -> str:
        try:
            from src.business.config_manager import ConfigManager
            cfg = ConfigManager()
            base = cfg.get("Study", "MaterialsDir", "")
            if base and os.path.isdir(base):
                return base
        except Exception:
            pass
        music_dir = os.path.join(os.path.expanduser("~"), "Music", "Music++", "StudyMaterials")
        os.makedirs(music_dir, exist_ok=True)
        return music_dir

    def import_from_url(
        self,
        url: str,
        subtitle_lang: str = "en",
        subtitle_lang_secondary: str = "",
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> Optional[StudyMaterial]:
        try:
            material_id = uuid.uuid4().hex[:12]
            output_dir = os.path.join(self.get_materials_dir(), material_id)
            os.makedirs(output_dir, exist_ok=True)

            options = ExtractOptions(
                subtitle_lang=subtitle_lang,
                subtitle_lang_secondary=subtitle_lang_secondary,
                prefer_manual_sub=True,
                extract_audio=True,
                extract_subtitle=True,
                audio_format="m4a",
                output_dir=output_dir,
            )

            result = self._extractor.extract_from_url(url, options, progress_callback)
            if not result.success:
                logger.error(f"StudyManager import_from_url failed: {result.error}")
                return None

            if not result.subtitle_path:
                logger.warning(f"StudyManager import_from_url: no subtitle found for '{result.title}', audio_path='{result.audio_path}'")
            else:
                logger.info(f"StudyManager import_from_url: subtitle_path='{result.subtitle_path}' for '{result.title}'")

            chapters_json = json.dumps(
                [{"index": ch.index, "title": ch.title, "start_ms": ch.start_ms, "end_ms": ch.end_ms}
                 for ch in result.chapters]
            )

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            material = StudyMaterial(
                id=material_id,
                title=result.title,
                source="url",
                source_url=url,
                audio_path=result.audio_path,
                subtitle_path=result.subtitle_path,
                subtitle_path_secondary=result.subtitle_path_secondary,
                chapters_json=chapters_json,
                duration_ms=result.duration_ms,
                created_at=now,
                last_played_at="",
                progress_ms=0,
            )

            self._db.insert("study_materials", {
                "id": material.id,
                "title": material.title,
                "source": material.source,
                "source_url": material.source_url,
                "audio_path": material.audio_path,
                "subtitle_path": material.subtitle_path,
                "subtitle_path_secondary": material.subtitle_path_secondary,
                "chapters_json": material.chapters_json,
                "duration_ms": material.duration_ms,
                "created_at": material.created_at,
                "last_played_at": material.last_played_at,
                "progress_ms": material.progress_ms,
            })

            if not material.subtitle_path:
                threading.Thread(
                    target=self._auto_segment_background,
                    args=(material.id,),
                    daemon=True,
                ).start()

            return material
        except Exception as e:
            logger.error(f"StudyManager import_from_url error: {e}")
            return None

    def import_from_file(
        self,
        file_path: str,
        progress_callback: Optional[Callable[[str, int], None]] = None,
        external_subtitle_path: str = "",
    ) -> Optional[StudyMaterial]:
        try:
            material_id = uuid.uuid4().hex[:12]
            output_dir = os.path.join(self.get_materials_dir(), material_id)
            os.makedirs(output_dir, exist_ok=True)

            is_audio_only = os.path.splitext(file_path)[1].lower() in [
                ".mp3", ".m4a", ".flac", ".wav", ".ogg", ".aac", ".wma", ".opus"
            ]

            if is_audio_only:
                audio_path = os.path.join(output_dir, os.path.basename(file_path))
                if not os.path.exists(audio_path):
                    import shutil
                    shutil.copy2(file_path, audio_path)

                subtitle_path = ""
                if external_subtitle_path and os.path.exists(external_subtitle_path):
                    sub_ext = os.path.splitext(external_subtitle_path)[1]
                    sub_dest = os.path.join(output_dir, f"{os.path.splitext(os.path.basename(file_path))[0]}{sub_ext}")
                    import shutil
                    shutil.copy2(external_subtitle_path, sub_dest)
                    subtitle_path = sub_dest
                else:
                    found = self._find_subtitle_near_audio(file_path)
                    if found:
                        import shutil
                        sub_dest = os.path.join(output_dir, os.path.basename(found))
                        shutil.copy2(found, sub_dest)
                        subtitle_path = sub_dest

                duration_ms = 0
                try:
                    from src.infrastructure.media_extractor import MediaExtractor
                    ext = MediaExtractor()
                    if ext._ffprobe:
                        import subprocess
                        cmd = [ext._ffprobe, "-i", audio_path, "-show_entries", "format=duration",
                               "-of", "json", "-v", "quiet"]
                        r = subprocess.run(cmd, capture_output=True, timeout=10)
                        if r.returncode == 0:
                            d = json.loads(r.stdout.decode())
                            duration_ms = int(float(d.get("format", {}).get("duration", 0)) * 1000)
                except Exception:
                    pass

                title = os.path.splitext(os.path.basename(file_path))[0]
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                material = StudyMaterial(
                    id=material_id,
                    title=title,
                    source="local",
                    source_url=file_path,
                    audio_path=audio_path,
                    subtitle_path=subtitle_path,
                    subtitle_path_secondary="",
                    chapters_json="[]",
                    duration_ms=duration_ms,
                    created_at=now,
                    last_played_at="",
                    progress_ms=0,
                )
                self._db.insert("study_materials", {
                    "id": material.id,
                    "title": material.title,
                    "source": material.source,
                    "source_url": material.source_url,
                    "audio_path": material.audio_path,
                    "subtitle_path": material.subtitle_path,
                    "subtitle_path_secondary": material.subtitle_path_secondary,
                    "chapters_json": material.chapters_json,
                    "duration_ms": material.duration_ms,
                    "created_at": material.created_at,
                    "last_played_at": material.last_played_at,
                    "progress_ms": material.progress_ms,
                })

                if not material.subtitle_path:
                    threading.Thread(
                        target=self._auto_segment_background,
                        args=(material.id,),
                        daemon=True,
                    ).start()

                return material

            options = ExtractOptions(
                extract_audio=True,
                extract_subtitle=True,
                audio_format="m4a",
                output_dir=output_dir,
            )

            result = self._extractor.extract_from_file(file_path, options, progress_callback)
            if not result.success:
                logger.error(f"StudyManager import_from_file failed: {result.error}")
                return None

            if external_subtitle_path and os.path.exists(external_subtitle_path):
                import shutil
                sub_ext = os.path.splitext(external_subtitle_path)[1]
                sub_dest = os.path.join(output_dir, f"{os.path.splitext(os.path.basename(file_path))[0]}{sub_ext}")
                shutil.copy2(external_subtitle_path, sub_dest)
                result.subtitle_path = sub_dest

            chapters_json = json.dumps(
                [{"index": ch.index, "title": ch.title, "start_ms": ch.start_ms, "end_ms": ch.end_ms}
                 for ch in result.chapters]
            )

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            material = StudyMaterial(
                id=material_id,
                title=result.title,
                source="local",
                source_url=file_path,
                audio_path=result.audio_path,
                subtitle_path=result.subtitle_path,
                subtitle_path_secondary="",
                chapters_json=chapters_json,
                duration_ms=result.duration_ms,
                created_at=now,
                last_played_at="",
                progress_ms=0,
            )

            self._db.insert("study_materials", {
                "id": material.id,
                "title": material.title,
                "source": material.source,
                "source_url": material.source_url,
                "audio_path": material.audio_path,
                "subtitle_path": material.subtitle_path,
                "subtitle_path_secondary": material.subtitle_path_secondary,
                "chapters_json": material.chapters_json,
                "duration_ms": material.duration_ms,
                "created_at": material.created_at,
                "last_played_at": material.last_played_at,
                "progress_ms": material.progress_ms,
            })

            if not material.subtitle_path:
                threading.Thread(
                    target=self._auto_segment_background,
                    args=(material.id,),
                    daemon=True,
                ).start()

            return material
        except Exception as e:
            logger.error(f"StudyManager import_from_file error: {e}")
            return None

    def scan_folder_for_media(self, folder_path: str) -> List[str]:
        media_exts = {
            ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".ts",
            ".mp3", ".m4a", ".flac", ".wav", ".ogg", ".aac", ".wma", ".opus",
        }
        found = []
        for root, dirs, files in os.walk(folder_path):
            for f in sorted(files):
                if os.path.splitext(f)[1].lower() in media_exts:
                    found.append(os.path.join(root, f))
        return found

    def import_from_folder(
        self,
        folder_path: str,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> List[StudyMaterial]:
        files = self.scan_folder_for_media(folder_path)
        if not files:
            logger.warning(f"import_from_folder: no media files found in {folder_path}")
            return []

        results = []
        total = len(files)
        for i, f in enumerate(files):
            if progress_callback:
                pct = int((i / total) * 100)
                progress_callback(f"导入 {i+1}/{total}: {os.path.basename(f)}", pct)
            mat = self.import_from_file(f)
            if mat:
                results.append(mat)

        if progress_callback:
            progress_callback(f"完成，成功导入 {len(results)}/{total} 个文件", 100)

        return results

    def get_materials(self) -> List[StudyMaterial]:
        try:
            rows = self._db.fetchall("SELECT * FROM study_materials ORDER BY created_at DESC")
            return [self._row_to_material(row) for row in rows]
        except Exception as e:
            logger.error(f"StudyManager get_materials error: {e}")
            return []

    def get_material(self, material_id: str) -> Optional[StudyMaterial]:
        try:
            row = self._db.fetchone("SELECT * FROM study_materials WHERE id = ?", (material_id,))
            if row:
                return self._row_to_material(row)
            return None
        except Exception as e:
            logger.error(f"StudyManager get_material error: {e}")
            return None

    def get_chapters(self, material_id: str) -> List[Chapter]:
        material = self.get_material(material_id)
        if material:
            return material.get_chapters()
        return []

    def get_subtitle_lines(self, material_id: str, chapter_index: int = -1) -> List[SubtitleLine]:
        material = self.get_material(material_id)
        if not material:
            logger.warning(f"get_subtitle_lines: material not found for id={material_id}")
            return []

        subtitle_path = material.subtitle_path
        logger.info(f"get_subtitle_lines: id={material_id}, subtitle_path='{subtitle_path}', audio_path='{material.audio_path}'")

        if not subtitle_path:
            logger.warning(f"get_subtitle_lines: subtitle_path is empty, trying fallback search in audio dir")
            subtitle_path = self._find_subtitle_near_audio(material.audio_path)
            if subtitle_path:
                logger.info(f"get_subtitle_lines: found subtitle via fallback: {subtitle_path}")
                self._db.update("study_materials", {"subtitle_path": subtitle_path}, "id = ?", (material_id,))
            else:
                logger.warning(f"get_subtitle_lines: no subtitle file found near audio: {material.audio_path}")
                return []

        if not os.path.exists(subtitle_path):
            logger.warning(f"get_subtitle_lines: subtitle file not found: {subtitle_path}, trying fallback")
            fallback = self._find_subtitle_near_audio(material.audio_path)
            if fallback:
                logger.info(f"get_subtitle_lines: found subtitle via fallback: {fallback}")
                self._db.update("study_materials", {"subtitle_path": fallback}, "id = ?", (material_id,))
                subtitle_path = fallback
            else:
                logger.warning(f"get_subtitle_lines: no subtitle file found near audio: {material.audio_path}")
                return []

        try:
            with open(subtitle_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            fmt = SubtitleParser.detect_format(subtitle_path)
            logger.info(f"get_subtitle_lines: parsing file={subtitle_path}, fmt={fmt}, content_len={len(content)}")
            lines = SubtitleParser.parse(content, fmt)
            logger.info(f"get_subtitle_lines: parsed {len(lines)} lines from {subtitle_path}")

            if material.subtitle_path_secondary and os.path.exists(material.subtitle_path_secondary):
                with open(material.subtitle_path_secondary, "r", encoding="utf-8", errors="ignore") as f:
                    content2 = f.read()
                fmt2 = SubtitleParser.detect_format(material.subtitle_path_secondary)
                secondary_lines = SubtitleParser.parse(content2, fmt2)
                lines = SubtitleParser.merge_translations(lines, secondary_lines)

            if chapter_index >= 0:
                chapters = material.get_chapters()
                if chapters and chapter_index < len(chapters):
                    ch = chapters[chapter_index]
                    ch_lines = SubtitleParser.split_by_chapter(lines, [ch])
                    lines = ch_lines.get(chapter_index, [])

            return lines
        except Exception as e:
            logger.error(f"StudyManager get_subtitle_lines error: {e}")
            return []

    def _auto_segment_background(self, material_id: str):
        try:
            logger.info(f"Auto-segmenting material {material_id} in background")
            self.run_segmentation(material_id)
        except Exception as e:
            logger.error(f"Auto-segment background error for {material_id}: {e}")

    def _find_subtitle_near_audio(self, audio_path: str) -> str:
        if not audio_path:
            return ""
        audio_dir = os.path.dirname(audio_path)
        if not audio_dir or not os.path.isdir(audio_dir):
            return ""
        for f in os.listdir(audio_dir):
            lower = f.lower()
            if any(lower.endswith(ext) for ext in [".srt", ".ass", ".ssa", ".vtt", ".lrc"]):
                return os.path.join(audio_dir, f)
        return ""

    def _get_segment_path(self, material_id: str) -> str:
        material = self.get_material(material_id)
        if not material:
            return ""
        audio_dir = os.path.dirname(material.audio_path)
        return os.path.join(audio_dir, "segments.json")

    def has_segment_file(self, material_id: str) -> bool:
        seg_path = self._get_segment_path(material_id)
        return bool(seg_path) and os.path.exists(seg_path)

    def save_segments(self, material_id: str, segments: list) -> str:
        seg_path = self._get_segment_path(material_id)
        if not seg_path:
            return ""
        data = []
        for seg in segments:
            data.append({
                "index": seg.index,
                "start_ms": seg.start_ms,
                "end_ms": seg.end_ms,
                "text": seg.text,
            })
        with open(seg_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(data)} segments to {seg_path}")
        return seg_path

    def load_segments(self, material_id: str) -> list:
        seg_path = self._get_segment_path(material_id)
        if not seg_path or not os.path.exists(seg_path):
            return []
        try:
            with open(seg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            segments = []
            for item in data:
                segments.append(SubtitleLine(
                    index=item.get("index", 0),
                    start_ms=item.get("start_ms", 0),
                    end_ms=item.get("end_ms", 0),
                    text=item.get("text", ""),
                ))
            logger.info(f"Loaded {len(segments)} segments from {seg_path}")
            return segments
        except Exception as e:
            logger.error(f"load_segments error: {e}")
            return []

    def run_segmentation(self, material_id: str, progress_callback=None) -> bool:
        material = self.get_material(material_id)
        if not material or not material.audio_path:
            logger.error(f"run_segmentation: invalid material {material_id}")
            return False
        if not os.path.exists(material.audio_path):
            logger.error(f"run_segmentation: audio file not found {material.audio_path}")
            return False

        try:
            from src.business.config_manager import ConfigManager
            cm = ConfigManager()
            threshold = int(cm.get("Study", "AutoSegSilenceThreshold", "0"))
            min_silence = int(cm.get("Study", "AutoSegMinSilenceMs", "300"))
            min_segment = int(cm.get("Study", "AutoSegMinSegmentMs", "800"))
        except Exception:
            threshold = 0
            min_silence = 300
            min_segment = 800

        logger.info(f"run_segmentation: {material.title}, threshold={threshold}, min_silence={min_silence}, min_segment={min_segment}")

        from src.infrastructure.audio_segmenter import AudioSegmenter
        segments = AudioSegmenter.detect_segments(
            material.audio_path,
            silence_threshold=threshold,
            min_silence_ms=min_silence,
            min_segment_ms=min_segment,
            progress_callback=progress_callback,
        )
        if segments:
            self.save_segments(material_id, segments)
            logger.info(f"run_segmentation: success, {len(segments)} segments saved")
            return True
        logger.warning(f"run_segmentation: failed for {material.title}, detect_segments returned None/empty")
        return False

    def run_whisper_transcription(
        self,
        material_id: str,
        audio_path: str,
        model_name: str = "base",
        language: str = "",
        device: str = "auto",
        hf_mirror_url: str = "",
        progress_callback=None,
    ) -> Optional[List[SubtitleLine]]:
        if not audio_path or not os.path.exists(audio_path):
            logger.error(f"run_whisper_transcription: audio file not found: {audio_path}")
            return None

        from src.plugins.whisper_plugin import WhisperPlugin
        plugin = WhisperPlugin()

        if not plugin.is_available():
            logger.error("run_whisper_transcription: faster-whisper not installed")
            return None

        if progress_callback:
            progress_callback("正在加载模型...", 5)

        subtitles = plugin.transcribe(
            audio_path,
            model_name=model_name,
            language=language if language else None,
            device=device,
            hf_mirror_url=hf_mirror_url,
            progress_callback=lambda pct: progress_callback("正在转录...", pct) if progress_callback else None,
        )

        if not subtitles:
            logger.warning(f"run_whisper_transcription: transcription returned no results for {material_id}")
            return None

        srt_path = self._save_srt(material_id, subtitles)
        if srt_path:
            self._db.update("study_materials", {"subtitle_path": srt_path}, "id = ?", (material_id,))
            logger.info(f"run_whisper_transcription: saved {len(subtitles)} subtitles to {srt_path}")

        return subtitles

    def _save_srt(self, material_id: str, subtitles: List[SubtitleLine]) -> str:
        material = self.get_material(material_id)
        if not material or not material.audio_path:
            return ""

        audio_dir = os.path.dirname(material.audio_path)
        base_name = os.path.splitext(os.path.basename(material.audio_path))[0]
        srt_path = os.path.join(audio_dir, f"{base_name}.srt")

        try:
            with open(srt_path, "w", encoding="utf-8") as f:
                for i, sub in enumerate(subtitles):
                    start_h = sub.start_ms // 3600000
                    start_m = (sub.start_ms % 3600000) // 60000
                    start_s = (sub.start_ms % 60000) // 1000
                    start_ms = sub.start_ms % 1000
                    end_h = sub.end_ms // 3600000
                    end_m = (sub.end_ms % 3600000) // 60000
                    end_s = (sub.end_ms % 60000) // 1000
                    end_ms = sub.end_ms % 1000

                    f.write(f"{i + 1}\n")
                    f.write(f"{start_h:02d}:{start_m:02d}:{start_s:02d},{start_ms:03d} --> "
                            f"{end_h:02d}:{end_m:02d}:{end_s:02d},{end_ms:03d}\n")
                    f.write(f"{sub.text}\n\n")

            logger.info(f"_save_srt: saved {len(subtitles)} lines to {srt_path}")
            return srt_path
        except Exception as e:
            logger.error(f"_save_srt error: {e}")
            return ""

    def re_extract_subtitle(self, material_id: str) -> bool:
        material = self.get_material(material_id)
        if not material:
            return False

        if material.subtitle_path and os.path.exists(material.subtitle_path):
            logger.info(f"re_extract_subtitle: subtitle already exists at {material.subtitle_path}")
            return True

        audio_dir = os.path.dirname(material.audio_path)
        if audio_dir and os.path.isdir(audio_dir):
            found = self._find_subtitle_near_audio(material.audio_path)
            if found:
                self._db.update("study_materials", {"subtitle_path": found}, "id = ?", (material_id,))
                logger.info(f"re_extract_subtitle: found subtitle near audio: {found}")
                return True

        if material.source == "url" and "bilibili.com" in material.source_url:
            extractor = MediaExtractor()
            subtitle_path = extractor._extract_bilibili_subtitle(
                material.source_url, audio_dir, ""
            )
            if subtitle_path:
                self._db.update("study_materials", {"subtitle_path": subtitle_path}, "id = ?", (material_id,))
                logger.info(f"re_extract_subtitle: Bilibili API found subtitle: {subtitle_path}")
                return True

        logger.warning(f"re_extract_subtitle: no subtitle found for material {material_id}")
        return False

    def get_audio_path(self, material_id: str, chapter_index: int = -1) -> str:
        material = self.get_material(material_id)
        if not material:
            return ""

        if chapter_index < 0:
            return material.audio_path

        chapters = material.get_chapters()
        if not chapters or chapter_index >= len(chapters):
            return material.audio_path

        output_dir = os.path.dirname(material.audio_path)
        split_dir = os.path.join(output_dir, "chapters")
        os.makedirs(split_dir, exist_ok=True)

        base_name = os.path.splitext(os.path.basename(material.audio_path))[0]
        ext = os.path.splitext(material.audio_path)[1] or ".m4a"
        ch = chapters[chapter_index]
        safe_title = "".join(c for c in ch.title if c.isalnum() or c in " _-").strip()
        if not safe_title:
            safe_title = f"chapter_{chapter_index + 1}"
        ch_path = os.path.join(split_dir, f"{base_name}_{safe_title}{ext}")

        if os.path.exists(ch_path):
            return ch_path

        split_paths = self._extractor.split_audio_by_chapter(
            material.audio_path, [ch], split_dir
        )
        if split_paths and os.path.exists(split_paths[0]):
            return split_paths[0]

        return material.audio_path

    def update_progress(self, material_id: str, progress_ms: int):
        try:
            self._db.update(
                "study_materials",
                {"progress_ms": progress_ms},
                "id = ?",
                (material_id,),
            )
        except Exception as e:
            logger.error(f"StudyManager update_progress error: {e}")

    def update_last_played(self, material_id: str):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            self._db.update(
                "study_materials",
                {"last_played_at": now},
                "id = ?",
                (material_id,),
            )
        except Exception as e:
            logger.error(f"StudyManager update_last_played error: {e}")

    def delete_material(self, material_id: str):
        try:
            material = self.get_material(material_id)
            if material:
                mat_dir = os.path.dirname(material.audio_path)
                if os.path.exists(mat_dir) and "StudyMaterials" in mat_dir:
                    import shutil
                    shutil.rmtree(mat_dir, ignore_errors=True)
            self._db.delete("study_materials", "id = ?", (material_id,))
            self._db.delete("study_records", "material_id = ?", (material_id,))
        except Exception as e:
            logger.error(f"StudyManager delete_material error: {e}")

    def _row_to_material(self, row: dict) -> StudyMaterial:
        return StudyMaterial(
            id=row.get("id", ""),
            title=row.get("title", ""),
            source=row.get("source", ""),
            source_url=row.get("source_url", ""),
            audio_path=row.get("audio_path", ""),
            subtitle_path=row.get("subtitle_path", ""),
            subtitle_path_secondary=row.get("subtitle_path_secondary", ""),
            chapters_json=row.get("chapters_json", "[]"),
            duration_ms=row.get("duration_ms", 0),
            created_at=row.get("created_at", ""),
            last_played_at=row.get("last_played_at", ""),
            progress_ms=row.get("progress_ms", 0),
        )
