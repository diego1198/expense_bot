"""
Voice transcription service using OpenAI Whisper.
Converts voice messages to text for expense parsing.
"""

import os
import tempfile
from pathlib import Path

from openai import AsyncOpenAI
import httpx

from src.config import config


class VoiceTranscriber:
    """Transcribe voice messages using OpenAI Whisper API."""
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
        self.model = config.WHISPER_MODEL
    
    async def transcribe_file(self, file_path: str) -> str:
        """
        Transcribe an audio file to text.
        
        Args:
            file_path: Path to the audio file
        
        Returns:
            Transcribed text
        """
        with open(file_path, "rb") as audio_file:
            response = await self.client.audio.transcriptions.create(
                model=self.model,
                file=audio_file,
                language="es",  # Spanish
                response_format="text"
            )
        
        return response.strip()
    
    async def transcribe_from_url(self, url: str, file_token: str = "") -> str:
        """
        Download and transcribe audio from URL.
        
        Args:
            url: URL to download the audio file
            file_token: Optional token for authentication
        
        Returns:
            Transcribed text
        """
        # Create temp file
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp_file:
            tmp_path = tmp_file.name
        
        try:
            # Download file
            async with httpx.AsyncClient() as client:
                response = await client.get(url, follow_redirects=True)
                response.raise_for_status()
                
                with open(tmp_path, "wb") as f:
                    f.write(response.content)
            
            # Transcribe
            return await self.transcribe_file(tmp_path)
        
        finally:
            # Clean up temp file
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    
    async def transcribe_telegram_voice(
        self, 
        bot, 
        file_id: str
    ) -> str:
        """
        Transcribe a Telegram voice message.
        
        Args:
            bot: Telegram bot instance
            file_id: Telegram file ID
        
        Returns:
            Transcribed text
        """
        # Get file info from Telegram
        file = await bot.get_file(file_id)
        file_url = file.file_path
        
        # For Telegram, we need to construct the full URL
        if not file_url.startswith("http"):
            file_url = f"https://api.telegram.org/file/bot{config.TELEGRAM_BOT_TOKEN}/{file_url}"
        
        return await self.transcribe_from_url(file_url)


# Singleton instance
voice_transcriber = VoiceTranscriber()
