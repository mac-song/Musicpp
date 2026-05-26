import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class SubtitleLine:
    index: int
    start_ms: int
    end_ms: int
    text: str
    translation: str = ""


@dataclass
class Chapter:
    index: int
    title: str
    start_ms: int
    end_ms: int = 0


class SubtitleParser:

    @staticmethod
    def parse(content: str, fmt: str) -> List[SubtitleLine]:
        fmt = fmt.lower().strip(".")
        if fmt == "srt":
            return SubtitleParser._parse_srt(content)
        elif fmt == "ass":
            return SubtitleParser._parse_ass(content)
        elif fmt == "vtt":
            return SubtitleParser._parse_vtt(content)
        elif fmt == "lrc":
            return SubtitleParser._parse_lrc(content)
        else:
            return SubtitleParser._auto_detect_parse(content)

    @staticmethod
    def _auto_detect_parse(content: str) -> List[SubtitleLine]:
        stripped = content.strip()
        if stripped.startswith("WEBVTT"):
            return SubtitleParser._parse_vtt(content)
        if "[Script Info]" in stripped:
            return SubtitleParser._parse_ass(content)
        if re.match(r"\d+\s*\n\d{2}:\d{2}", stripped):
            return SubtitleParser._parse_srt(content)
        if re.match(r"\[\d{2}:\d{2}", stripped):
            return SubtitleParser._parse_lrc(content)
        return SubtitleParser._parse_srt(content)

    @staticmethod
    def _parse_srt(content: str) -> List[SubtitleLine]:
        lines = []
        blocks = re.split(r"\n\s*\n", content.strip())
        idx = 0
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            parts = block.split("\n", 2)
            if len(parts) < 2:
                continue
            time_match = re.match(
                r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})",
                parts[1].strip(),
            )
            if not time_match:
                continue
            start_ms = (
                int(time_match.group(1)) * 3600000
                + int(time_match.group(2)) * 60000
                + int(time_match.group(3)) * 1000
                + int(time_match.group(4))
            )
            end_ms = (
                int(time_match.group(5)) * 3600000
                + int(time_match.group(6)) * 60000
                + int(time_match.group(7)) * 1000
                + int(time_match.group(8))
            )
            text = parts[2].strip() if len(parts) > 2 else ""
            text = re.sub(r"<[^>]+>", "", text)
            text = text.replace("\\N", "\n").replace("\\n", "\n")
            if not text:
                continue
            lines.append(SubtitleLine(index=idx, start_ms=start_ms, end_ms=end_ms, text=text))
            idx += 1
        return lines

    @staticmethod
    def _parse_ass(content: str) -> List[SubtitleLine]:
        lines = []
        idx = 0
        in_events = False
        format_fields = []
        for raw_line in content.split("\n"):
            line = raw_line.strip()
            if line.startswith("[Events]"):
                in_events = True
                continue
            if line.startswith("[") and in_events:
                break
            if not in_events:
                continue
            if line.startswith("Format:"):
                format_fields = [f.strip() for f in line[len("Format:"):].split(",")]
                continue
            if line.startswith("Dialogue:"):
                parts = line[len("Dialogue:"):].strip().split(",", len(format_fields) - 1)
                if len(parts) < len(format_fields):
                    continue
                field_map = {}
                for i, field_name in enumerate(format_fields):
                    if i < len(parts):
                        field_map[field_name] = parts[i].strip()
                start_ms = SubtitleParser._parse_ass_time(field_map.get("Start", "0:00:00.00"))
                end_ms = SubtitleParser._parse_ass_time(field_map.get("End", "0:00:00.00"))
                text = field_map.get("Text", "")
                text = re.sub(r"\{[^}]*\}", "", text)
                text = text.replace("\\N", "\n").replace("\\n", "\n")
                text = text.strip()
                if not text:
                    continue
                lines.append(SubtitleLine(index=idx, start_ms=start_ms, end_ms=end_ms, text=text))
                idx += 1
        return lines

    @staticmethod
    def _parse_ass_time(time_str: str) -> int:
        match = re.match(r"(\d+):(\d{2}):(\d{2})\.(\d{2})", time_str)
        if not match:
            return 0
        h = int(match.group(1))
        m = int(match.group(2))
        s = int(match.group(3))
        cs = int(match.group(4))
        return h * 3600000 + m * 60000 + s * 1000 + cs * 10

    @staticmethod
    def _parse_vtt(content: str) -> List[SubtitleLine]:
        lines = []
        idx = 0
        body = content
        header_end = content.find("\n\n")
        if header_end >= 0:
            body = content[header_end + 2:]
        blocks = re.split(r"\n\s*\n", body.strip())
        for block in blocks:
            block = block.strip()
            if not block or block.startswith("NOTE") or block.startswith("STYLE"):
                continue
            time_match = re.search(
                r"(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})\.(\d{3})",
                block,
            )
            if not time_match:
                time_match = re.search(
                    r"(\d{2}):(\d{2})\.(\d{3})\s*-->\s*(\d{2}):(\d{2})\.(\d{3})",
                    block,
                )
                if time_match:
                    start_ms = int(time_match.group(1)) * 60000 + int(time_match.group(2)) * 1000 + int(time_match.group(3))
                    end_ms = int(time_match.group(4)) * 60000 + int(time_match.group(5)) * 1000 + int(time_match.group(6))
                else:
                    continue
            else:
                start_ms = (
                    int(time_match.group(1)) * 3600000
                    + int(time_match.group(2)) * 60000
                    + int(time_match.group(3)) * 1000
                    + int(time_match.group(4))
                )
                end_ms = (
                    int(time_match.group(5)) * 3600000
                    + int(time_match.group(6)) * 60000
                    + int(time_match.group(7)) * 1000
                    + int(time_match.group(8))
                )
            text_lines = block.split("\n")[1:]
            text = "\n".join(text_lines).strip()
            text = re.sub(r"<[^>]+>", "", text)
            if not text:
                continue
            lines.append(SubtitleLine(index=idx, start_ms=start_ms, end_ms=end_ms, text=text))
            idx += 1
        return lines

    @staticmethod
    def _parse_lrc(content: str) -> List[SubtitleLine]:
        lines = []
        idx = 0
        pattern = re.compile(r"\[(\d{2}):(\d{2})\.(\d{2,3})\](.*)")
        for raw_line in content.split("\n"):
            line = raw_line.strip()
            match = pattern.match(line)
            if not match:
                continue
            minutes = int(match.group(1))
            seconds = int(match.group(2))
            milliseconds = int(match.group(3))
            if len(match.group(3)) == 2:
                milliseconds *= 10
            text = match.group(4).strip()
            time_ms = minutes * 60000 + seconds * 1000 + milliseconds
            lines.append(SubtitleLine(index=idx, start_ms=time_ms, end_ms=0, text=text))
            idx += 1
        for i in range(len(lines) - 1):
            lines[i].end_ms = lines[i + 1].start_ms
        return lines

    @staticmethod
    def to_lrc(lines: List[SubtitleLine]) -> str:
        result = []
        for line in lines:
            minutes = line.start_ms // 60000
            seconds = (line.start_ms % 60000) // 1000
            milliseconds = line.start_ms % 1000
            result.append(f"[{minutes:02d}:{seconds:02d}.{milliseconds:03d}]{line.text}")
        return "\n".join(result)

    @staticmethod
    def to_srt(lines: List[SubtitleLine]) -> str:
        result = []
        for line in lines:
            start_h = line.start_ms // 3600000
            start_m = (line.start_ms % 3600000) // 60000
            start_s = (line.start_ms % 60000) // 1000
            start_ms = line.start_ms % 1000
            end_h = line.end_ms // 3600000
            end_m = (line.end_ms % 3600000) // 60000
            end_s = (line.end_ms % 60000) // 1000
            end_ms_val = line.end_ms % 1000
            result.append(str(line.index + 1))
            result.append(
                f"{start_h:02d}:{start_m:02d}:{start_s:02d},{start_ms:03d} --> "
                f"{end_h:02d}:{end_m:02d}:{end_s:02d},{end_ms_val:03d}"
            )
            result.append(line.text)
            result.append("")
        return "\n".join(result)

    @staticmethod
    def split_by_chapter(
        lines: List[SubtitleLine], chapters: List[Chapter]
    ) -> Dict[int, List[SubtitleLine]]:
        if not chapters:
            return {0: lines}
        result = {}
        for ch in chapters:
            ch_lines = []
            for line in lines:
                if ch.end_ms > 0:
                    if line.start_ms >= ch.start_ms and line.start_ms < ch.end_ms:
                        ch_lines.append(line)
                else:
                    if line.start_ms >= ch.start_ms:
                        ch_lines.append(line)
            result[ch.index] = ch_lines
        return result

    @staticmethod
    def auto_split_sentences(
        lines: List[SubtitleLine], gap_ms: int = 2000
    ) -> List[SubtitleLine]:
        if not lines:
            return []
        merged = [SubtitleLine(
            index=0,
            start_ms=lines[0].start_ms,
            end_ms=lines[0].end_ms,
            text=lines[0].text,
            translation=lines[0].translation,
        )]
        for i in range(1, len(lines)):
            prev = merged[-1]
            curr = lines[i]
            if curr.start_ms - prev.end_ms <= gap_ms:
                prev.end_ms = curr.end_ms
                if prev.text and curr.text:
                    prev.text += " " + curr.text
                else:
                    prev.text = prev.text or curr.text
                if curr.translation:
                    if prev.translation:
                        prev.translation += " " + curr.translation
                    else:
                        prev.translation = curr.translation
            else:
                merged.append(SubtitleLine(
                    index=len(merged),
                    start_ms=curr.start_ms,
                    end_ms=curr.end_ms,
                    text=curr.text,
                    translation=curr.translation,
                ))
        return merged

    @staticmethod
    def merge_translations(
        primary: List[SubtitleLine], secondary: List[SubtitleLine]
    ) -> List[SubtitleLine]:
        if not secondary:
            return primary
        if not primary:
            return secondary
        for p_line in primary:
            best_match = None
            best_dist = float("inf")
            for s_line in secondary:
                dist = abs(p_line.start_ms - s_line.start_ms)
                if dist < best_dist:
                    best_dist = dist
                    best_match = s_line
            if best_match and best_dist < 2000:
                p_line.translation = best_match.text
        return primary

    @staticmethod
    def detect_format(file_path: str) -> str:
        ext = file_path.lower().rsplit(".", 1)[-1] if "." in file_path else ""
        if ext in ("srt", "ass", "ssa", "vtt", "lrc"):
            return ext if ext != "ssa" else "ass"
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                head = f.read(1024)
            if head.startswith("WEBVTT"):
                return "vtt"
            if "[Script Info]" in head:
                return "ass"
            if re.match(r"\[\d{2}:\d{2}", head.strip()):
                return "lrc"
        except Exception:
            pass
        return "srt"
