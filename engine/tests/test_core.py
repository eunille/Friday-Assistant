"""Config, paths, sentence splitting and the gibberish filter."""
from pathlib import Path

from friday.core import config, paths
from friday.voice.tts.speaker import _split_sentences


def test_deep_merge_keeps_defaults_and_does_not_mutate():
    defaults = {"stt": {"model": "base", "language": "en"}, "x": 1}
    merged = config._deep_merge(defaults, {"stt": {"model": "small"}, "y": 2})
    assert merged == {"stt": {"model": "small", "language": "en"}, "x": 1, "y": 2}
    assert defaults["stt"]["model"] == "base"


def test_load_config_reads_file_over_defaults(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("stt:\n  model: tiny\n", encoding="utf-8")
    monkeypatch.setattr(config, "_CONFIG", None)
    loaded = config.load_config(str(cfg_file))
    assert loaded["stt"]["model"] == "tiny"
    assert loaded["assistant"]["name"] == "Friday"
    monkeypatch.setattr(config, "_CONFIG", None)


def test_missing_config_file_falls_back_to_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "_CONFIG", None)
    loaded = config.load_config(str(tmp_path / "nope.yaml"))
    assert loaded["wake_word"]["engine"] == "openwakeword"
    monkeypatch.setattr(config, "_CONFIG", None)


def test_shipped_config_is_found_and_has_no_elevenlabs():
    assert paths.CONFIG_FILE.is_file()
    assert "eleven" not in paths.CONFIG_FILE.read_text(encoding="utf-8").lower()


def test_resolve_anchors_relative_paths_at_home():
    assert paths.resolve("logs/friday.log") == paths.HOME / "logs" / "friday.log"
    absolute = Path(__file__).resolve()
    assert paths.resolve(absolute) == absolute


def test_split_sentences_on_punctuation():
    assert _split_sentences("Bitcoin's up. Strongest move in weeks!") == [
        "Bitcoin's up.", "Strongest move in weeks!",
    ]


def test_split_sentences_breaks_long_ones_at_commas():
    long = ("one two three four five six seven eight nine ten, "
            "eleven twelve thirteen fourteen fifteen sixteen seventeen")
    parts = _split_sentences(long)
    assert len(parts) == 2 and all(len(p.split()) <= 15 for p in parts)


def test_split_sentences_never_returns_empty():
    assert _split_sentences("hello") == ["hello"]


def test_is_meaningful_filters_filler_only_speech():
    from friday.app import _is_meaningful
    assert not _is_meaningful("uh this is")
    assert not _is_meaningful("um, okay.")
    assert _is_meaningful("open youtube")


def test_woof_speaks_each_sentence_in_order_and_converts_audio(monkeypatch):
    import numpy as np
    from friday.voice.tts import woof

    monkeypatch.setattr(woof, "_get", lambda: (lambda text, seed=None: np.full(4, 0.5, dtype=np.float32)))
    played = []
    ok = woof.speak_woof("One. Two.", split=lambda t: ["One.", "", "Two."],
                         play=lambda samples, rate: played.append((samples.dtype, int(samples[0]), rate)))
    assert ok and played == [(np.dtype("int16"), 16383, 24000)] * 2


def test_woof_reports_failure_so_the_caller_can_fall_back(monkeypatch):
    from friday.voice.tts import woof

    def broken():
        raise RuntimeError("no model")

    monkeypatch.setattr(woof, "_get", broken)
    assert woof.speak_woof("hello", play=lambda *a: None) is False


def test_woof_clips_out_of_range_audio():
    import numpy as np
    from friday.voice.tts import woof
    assert woof.to_int16(np.array([2.0, -2.0, 0.0])).tolist() == [32767, -32767, 0]
