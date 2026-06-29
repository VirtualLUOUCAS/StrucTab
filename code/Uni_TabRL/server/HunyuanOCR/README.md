## HunyuanOCR (Anchor OCR) vLLM service

We use the open-source HunyuanOCR model as the Anchor OCR model for the
Anchor-Guided Destylization content reward. Optionally, EAGLE-3 speculative
decoding can be enabled to accelerate inference.

Model paths (fill in your own):

```bash
model_path="your/path/to/HunyuanOCR"
draft_model_path="your/path/to/HunyuanOCR-eagle3"
```

You can download the HunyuanOCR model from [HuggingFace](https://huggingface.co/tencent/HunyuanOCR) and the EAGLE-3 draft model from [HuggingFace](https://huggingface.co/AngelSlim/HunyuanOCR_eagle3).

Launch the service with `run.sh` (adjust GPU range, port range and model paths at the top of the script), then register the resulting `host:port` endpoints in `Uni_TabRL/configs/servers/hunyuan_ocr.json`.
