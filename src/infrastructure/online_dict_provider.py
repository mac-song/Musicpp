import json
import re
import traceback
from typing import Callable, Optional

from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class OnlineDictProvider:

    @staticmethod
    def lookup_youdao(word: str, timeout: int = 5) -> Optional[dict]:
        try:
            from urllib.request import urlopen, Request
            from urllib.parse import quote

            url = f"https://dict.youdao.com/suggest?num=1&doctype=json&q={quote(word)}"
            req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urlopen(req, timeout=timeout)
            data = json.loads(resp.read().decode("utf-8"))

            entries = data.get("data", {}).get("entries", [])
            if not entries:
                return None

            entry = entries[0]
            explain = entry.get("explain", "")
            if not explain:
                return None

            return {
                "word": entry.get("entry", word),
                "phonetic": "",
                "translation": explain,
                "definition": "",
                "pos": "",
                "source": "youdao",
            }
        except Exception as e:
            logger.debug(f"Youdao lookup failed for '{word}': {e}")
            return None

    @staticmethod
    def lookup_youdao_detail(word: str, timeout: int = 5) -> Optional[dict]:
        try:
            from urllib.request import urlopen, Request
            from urllib.parse import quote

            url = f"https://dict.youdao.com/jsonapi?q={quote(word)}"
            req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urlopen(req, timeout=timeout)
            data = json.loads(resp.read().decode("utf-8"))

            result = {
                "word": word,
                "phonetic": "",
                "translation": "",
                "definition": "",
                "pos": "",
                "source": "youdao",
            }

            ec = data.get("ec", {})
            if ec:
                word_data = ec.get("word", [{}])[0] if ec.get("word") else {}
                trs = ec.get("tr", [])
                if trs:
                    trans_parts = []
                    for tr in trs:
                        l_i = tr.get("l", {}).get("i", "")
                        if l_i:
                            trans_parts.append(l_i)
                    result["translation"] = "\n".join(trans_parts)

            meta = data.get("meta", {})
            if meta:
                result["phonetic"] = meta.get("inputPhonetic", "") or ""

            simple = data.get("simple", {})
            if simple and simple.get("word"):
                for w in simple["word"]:
                    if not result["phonetic"]:
                        result["phonetic"] = w.get("ukphone", "") or w.get("usphone", "") or ""

            return result if result["translation"] else None

        except Exception as e:
            logger.debug(f"Youdao detail lookup failed for '{word}': {e}")
            return None

    @staticmethod
    def lookup_freedict(word: str, timeout: int = 5) -> Optional[dict]:
        try:
            from urllib.request import urlopen, Request

            url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
            req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urlopen(req, timeout=timeout)
            data = json.loads(resp.read().decode("utf-8"))

            if not data or not isinstance(data, list):
                return None

            entry = data[0]
            phonetic = entry.get("phonetic", "")
            if not phonetic:
                for p in entry.get("phonetics", []):
                    if p.get("text"):
                        phonetic = p["text"]
                        break

            meanings = entry.get("meanings", [])
            def_parts = []
            trans_parts = []
            pos_parts = []

            for m in meanings:
                pos = m.get("partOfSpeech", "")
                if pos:
                    pos_parts.append(pos)
                for d in m.get("definitions", []):
                    line = f"{pos} {d.get('definition', '')}" if pos else d.get("definition", "")
                    def_parts.append(line)

            result = {
                "word": entry.get("word", word),
                "phonetic": phonetic,
                "translation": "",
                "definition": "\n".join(def_parts) if def_parts else "",
                "pos": ", ".join(pos_parts) if pos_parts else "",
                "source": "freedict",
            }
            return result if result["definition"] else None

        except Exception as e:
            logger.debug(f"FreeDict lookup failed for '{word}': {e}")
            return None

    @staticmethod
    def lookup_kingsoft(word: str, timeout: int = 5) -> Optional[dict]:
        try:
            from urllib.request import urlopen, Request
            import xml.etree.ElementTree as ET

            url = f"http://dict-co.iciba.com/api/dictionary.php?type=json&w={word}&key=00000000000000000000000000000"
            req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urlopen(req, timeout=timeout)
            raw = resp.read().decode("utf-8")

            try:
                data = json.loads(raw)
                if not data:
                    return None

                result = {
                    "word": word,
                    "phonetic": "",
                    "translation": "",
                    "definition": "",
                    "pos": "",
                    "source": "kingsoft",
                }

                symbols = data.get("symbols", [])
                if symbols:
                    s = symbols[0]
                    result["phonetic"] = s.get("ph_am", "") or s.get("ph_en", "") or ""
                    parts = s.get("parts", [])
                    trans_lines = []
                    for p in parts:
                        part_pos = p.get("part", "")
                        means = p.get("means", [])
                        if isinstance(means, list):
                            mean_str = "; ".join(m if isinstance(m, str) else m.get("m", "") for m in means)
                        else:
                            mean_str = str(means)
                        if part_pos:
                            trans_lines.append(f"{part_pos} {mean_str}")
                        else:
                            trans_lines.append(mean_str)
                    result["translation"] = "\n".join(trans_lines)

                return result if result["translation"] else None

            except json.JSONDecodeError:
                pass

            try:
                root = ET.fromstring(raw)
                result = {
                    "word": word,
                    "phonetic": "",
                    "translation": "",
                    "definition": "",
                    "pos": "",
                    "source": "kingsoft",
                }

                phon = root.find(".//ps")
                if phon is not None and phon.text:
                    result["phonetic"] = f"/{phon.text}/"

                trans_parts = []
                for pos_node in root.findall(".//pos"):
                    pos_text = pos_node.text or ""
                    accept = pos_node.find("../acceptation")
                    if accept is not None and accept.text:
                        trans_parts.append(f"{pos_text} {accept.text.strip()}")
                if trans_parts:
                    result["translation"] = "\n".join(trans_parts)

                return result if result["translation"] else None
            except Exception:
                return None

        except Exception as e:
            logger.debug(f"Kingsoft lookup failed for '{word}': {e}")
            return None

    @staticmethod
    def lookup_any(word: str, timeout: int = 5) -> Optional[dict]:
        for method in [
            OnlineDictProvider.lookup_youdao,
            OnlineDictProvider.lookup_kingsoft,
            OnlineDictProvider.lookup_freedict,
        ]:
            try:
                result = method(word, timeout=timeout)
                if result and (result.get("translation") or result.get("definition")):
                    return result
            except Exception:
                continue
        return None
