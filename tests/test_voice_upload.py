"""Uploading the voice includes the wait for it to replicate, so the pipeline
and scripts/pronunciation_check.py wait the same."""

import time

import pytest

import src.audio as audio


class _Uploaded:
    status_code = 200

    def json(self):
        return {"voice_id": "v1"}


@pytest.mark.parametrize("delay, waits", [(7, [7]), (0, [])])
def test_upload_waits_the_configured_replication_delay(tmp_path, monkeypatch, delay, waits):
    sample = tmp_path / "voice.wav"
    sample.write_bytes(b"RIFF")
    slept: list[float] = []
    # httpx.post is DeepInfra's voice-upload endpoint (network); time.sleep is
    # recorded instead of waited.
    monkeypatch.setattr(audio.httpx, "post", lambda *a, **kw: _Uploaded())
    monkeypatch.setattr(audio, "VOICE_UPLOAD_DELAY_SECONDS", delay)
    monkeypatch.setattr(time, "sleep", slept.append)

    assert audio.upload_voice_to_deepinfra(sample, "key") == "v1"
    assert slept == waits
