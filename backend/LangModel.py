import multiprocessing
import os
from queue import Empty
from threading import Thread

import whisper
from tinydb import Query, where

from transcribe import transcribe


class LangModel:
    def __init__(self):
        self.model = None
        self.index = 0
        self.q = None
        # Use environment variable for model name, fallback to tiny
        self.model_name = os.getenv("WHISPER_MODEL_NAME", "tiny")
        # self.model_name = 'large-v2'
        self.process_queues = dict()
        self.active_threads = dict()
        self.load_lang_model()

    def load_lang_model(self):
        # Use environment variable for model directory, fallback to local models dir
        model_path = os.getenv("WHISPER_MODEL_DIR") or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "models"
        )
        print(f"Load Model: {self.model_name} into {model_path}")
        self.model = whisper.load_model(self.model_name, download_root=model_path)
        # self.model = whisper.load_model("tiny")
        print("finished")

    def transcribe_text(self, audio_file, transcript_id, end_callback):

        if self.model is None:
            self.load_lang_model()

        q = multiprocessing.Queue()
        self.process_queues[transcript_id] = q

        kwargs = dict(
            model=self.model,
            audio=audio_file,
            verbose=True,
            fp16=False,
            language="de",
            process_queue=q,
            job_id=transcript_id,
            end_callback=end_callback,
        )

        p = Thread(target=transcribe, kwargs=kwargs)
        self.active_threads[transcript_id] = p
        p.start()

    def stop_transcription(self, transcript_id):
        """Stop a running transcription process"""
        if transcript_id not in self.process_queues:
            return False

        # Signal the process to stop by putting a stop message in the queue
        self.process_queues[transcript_id].put(
            {"channel": "control", "data": "stop", "job_id": transcript_id}
        )

        # Put an end message to finalize the process
        self.process_queues[transcript_id].put(
            {"channel": "message", "data": "end", "job_id": transcript_id}
        )

        # Clean up references
        if transcript_id in self.active_threads:
            del self.active_threads[transcript_id]

        return True

    def empty_process_queue(self, job_id):
        process_queue = self.process_queues.get(job_id)
        if process_queue is None:
            yield [], False

        while True:
            try:
                data = process_queue.get_nowait()
            except Empty as e:
                break

            if data["data"] == "end":
                yield {}, True
            elif data["channel"] == "message":
                yield dict(
                    start=data["data"]["start"],
                    end=data["data"]["end"],
                    text=data["data"]["text"],
                    copy=data["data"]["copy"],
                ), False


if __name__ == "__main__":
    lang_model = LangModel()
