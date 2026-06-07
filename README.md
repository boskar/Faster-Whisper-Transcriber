<div align="center">

<img width="621" height="367" alt="image" src="https://github.com/user-attachments/assets/7fa15938-5c18-424b-8f2b-83b30380e523" />

### Reliably transcribe your voice or an audio file on CPU or GPU!

<img width="1090" height="220" alt="image" src="https://github.com/user-attachments/assets/76908cd1-954c-4752-94a4-6423ec610b1e" />

<br>
</div>

## Aim of the fork

- Phlips SpeechMike Integration - robust, multiplatform (Linux, MacOS and Windows), using HID API (without need of Philips SpeechControl).
- Client Mode - ulitmately as third lightweight, non-GPU, non-CPU, "remote whisper inference mode"
- Text curation using LLM (?) 

## Features

- Voice recording with real-time waveform visualization
- Single file and batch (multi-file) transcription
- Recursive directory scanning for batch processing
- Configurable file type filtering
- Multiple output formats: txt, srt, vtt, tsv, json
- Output to clipboard, source directory, or custom directory
- Real-time system monitoring (CPU, RAM, GPU, VRAM, Power)
- Global hotkey support
- Dockable clipboard and file transcription panels
- All settings persisted between sessions

## Supported Models

Uses the [faster-whisper](https://github.com/SYSTRAN/faster-whisper) library, which provides CTranslate2-based inference for OpenAI's Whisper models.  Supports both transcription and translation tasks depending on the model selected.

## 💻 Install And Run from Virtual Environment
> Download the latest release...unzip and extract...go to the directory containing ```main.py```...run these commands in order:
```
python -m venv .
```
```
.\Scripts\activate
```
```
python install.py
```
```
python main.py
```
