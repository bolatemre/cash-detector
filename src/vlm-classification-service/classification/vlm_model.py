import logging
from typing import Any

from PIL import Image
from qwen_vl_utils import process_vision_info
from transformers import AutoModelForImageTextToText, AutoProcessor

from config.settings import Settings

logger = logging.getLogger(__name__)


class VlmModel:
    """Loads Qwen-VL and runs generation on extracted frames."""

    def __init__(self, settings: Settings):
        self._settings = settings
        logger.info("Loading VLM model %s ...", settings.model_name)
        self._model = AutoModelForImageTextToText.from_pretrained(
            settings.model_name,
            dtype=settings.dtype,
            device_map=settings.device_map,
            max_memory=settings.parsed_max_memory(),
        )
        self._processor = AutoProcessor.from_pretrained(settings.model_processor)
        logger.info("VLM model loaded successfully")

    def generate(self, frames: list[Image.Image], effective_fps: float) -> str:
        messages = [
            {"role": "system", "content": self._settings.system_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "video",
                        "video": frames,
                        "sample_fps": effective_fps,
                    },
                    {
                        "type": "text",
                        "text": self._settings.user_prompt,
                    },
                ],
            },
        ]

        text = self._processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        images, videos, video_kwargs = process_vision_info(
            messages,
            image_patch_size=16,
            return_video_kwargs=True,
            return_video_metadata=True,
        )

        if videos is not None:
            videos, video_metadatas = zip(*videos)
            videos, video_metadatas = list(videos), list(video_metadatas)
        else:
            video_metadatas = None

        inputs = self._processor(
            text=text,
            images=images,
            videos=videos,
            video_metadata=video_metadatas,
            return_tensors="pt",
            do_resize=False,
            **video_kwargs,
        ).to(self._model.device)

        generation_kwargs: dict[str, Any] = {
            "max_new_tokens": self._settings.max_new_tokens,
            "do_sample": self._settings.do_sample,
        }
        if self._settings.do_sample:
            generation_kwargs.update(
                {
                    "temperature": self._settings.temperature,
                    "top_p": self._settings.top_p,
                    "top_k": self._settings.top_k,
                    "repetition_penalty": self._settings.repetition_penalty,
                }
            )

        generated_ids = self._model.generate(**inputs, **generation_kwargs)
        generated_ids_trimmed = [
            out_ids[len(in_ids):]
            for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        output_text = self._processor.batch_decode(
            generated_ids_trimmed,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )
        return output_text[0]
