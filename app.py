import os
import re
import json
import time
import logging
from pathlib import Path
import shutil
import requests

import eyed3
import mutagen
from mutagen.oggopus import OggOpus
from mutagen.id3 import ID3NoHeaderError
from tqdm import tqdm

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("metadata_updater.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Hardcoded configuration
INPUT_FOLDER = "input"
OUTPUT_FOLDER = "output"
OLLAMA_BASE_URL = "http://localhost:11434"  # Default Ollama URL
OLLAMA_MODEL = "llama3.2"  # Change this to your preferred Ollama model
BATCH_SIZE = 10
RATE_LIMIT_DELAY = 1.0
OVERWRITE = True
INTERACTIVE_MODE = True  # Set to False to skip confirmation prompts

class AudioMetadataGenerator:
    def __init__(self):
        """
        Initialize the Audio metadata generator with hardcoded values for Ollama.
        """
        self.input_folder = Path(INPUT_FOLDER)
        self.output_folder = Path(OUTPUT_FOLDER)
        self.ollama_base_url = OLLAMA_BASE_URL
        self.model = OLLAMA_MODEL
        self.batch_size = BATCH_SIZE
        self.rate_limit_delay = RATE_LIMIT_DELAY
        self.overwrite = OVERWRITE
        self.interactive_mode = INTERACTIVE_MODE
        
        # Ensure folders exist
        if not self.input_folder.exists():
            raise FileNotFoundError(f"Input folder not found: {self.input_folder}")
        
        if not self.output_folder.exists():
            logger.info(f"Creating output folder: {self.output_folder}")
            self.output_folder.mkdir(parents=True, exist_ok=True)
            
        # Test Ollama connection
        try:
            self.test_ollama_connection()
            logger.info(f"Successfully connected to Ollama with model: {self.model}")
        except Exception as e:
            logger.error(f"Failed to connect to Ollama: {e}")
            raise

        # Statistics for reporting
        self.stats = {
            "total_files": 0,
            "processed_files": 0,
            "success": 0,
            "errors": 0,
            "skipped": 0
        }
        
    def test_ollama_connection(self):
        """Test connection to Ollama server."""
        try:
            response = requests.get(f"{self.ollama_base_url}/api/tags")
            response.raise_for_status()
            
            # Check if our model is available
            models = response.json().get("models", [])
            model_names = [model["name"] for model in models]
            
            if not any(self.model in name for name in model_names):
                logger.warning(f"Model '{self.model}' not found. Available models: {model_names}")
                logger.warning(f"You may need to run: ollama pull {self.model}")
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"Cannot connect to Ollama at {self.ollama_base_url}. Make sure Ollama is running. Error: {e}")
    
    def get_audio_files(self):
        """Find all audio files (MP3 and Opus) in the input folder."""
        try:
            mp3_files = list(self.input_folder.glob("**/*.mp3"))
            opus_files = list(self.input_folder.glob("**/*.opus"))
            all_files = mp3_files + opus_files
            
            logger.info(f"Found {len(mp3_files)} MP3 files and {len(opus_files)} Opus files in {self.input_folder}")
            logger.info(f"Total audio files: {len(all_files)}")
            
            self.stats["total_files"] = len(all_files)
            return all_files
        except Exception as e:
            logger.error(f"Error finding audio files: {e}")
            return []
    
    def clean_filename(self, filename):
        """Extract and clean the song name from the filename."""
        # Remove file extension
        name = os.path.splitext(filename)[0]
        
        # Remove common prefixes, numbering, etc.
        name = re.sub(r'^\d+[\s_\-\.]+', '', name)  # Remove leading numbers with separators
        name = re.sub(r'^\[.*?\][\s_\-\.]*', '', name)  # Remove bracketed text at start
        
        # Check if it's in "Artist - Title" format and preserve the structure for AI processing
        # Don't strip the artist part here - let the AI handle the separation
        
        # Replace underscores and dots with spaces, but keep dashes for "Artist - Title" detection
        name = re.sub(r'[_\.]+', ' ', name)
        
        # Remove extra spaces but keep single dashes
        name = re.sub(r'\s+', ' ', name).strip()
        
        return name
    
    def get_metadata_from_ollama(self, song_name, existing_metadata=None):
        """Query Ollama to get metadata for a song."""
        
        # Create context about existing metadata
        existing_context = ""
        if existing_metadata:
            non_empty_fields = {k: v for k, v in existing_metadata.items() if v and v != "(empty)"}
            if non_empty_fields:
                existing_context = f"\n\nExisting metadata in the file:\n{json.dumps(non_empty_fields, indent=2)}\nPlease use this existing information when it's correct, and only suggest changes when you can provide better/more accurate information."
        
        prompt = f"""I need detailed metadata for the song with filename "{song_name}". 

IMPORTANT RULES:
1. For the title field, provide ONLY the song title without artist names
2. Do NOT include artist names in the title - keep them separate in the artists field
3. If the filename contains "Artist - Song Title", extract just "Song Title" for the title field

Please provide the following information in JSON format:
- title: The song title ONLY (no artist names)
- artists: The performers/singers of the song (as a comma-separated string)
- album: The album name or compilation it's from
- year: The release year (as a number)
- composer: The composer/producer/music director
- genre: The primary genre of the song
- language: The language of the song's lyrics

Return ONLY a JSON object with these fields. If uncertain about any field, provide your best guess. If you cannot determine a field, use null.

Example format:
{{"title": "Yesterday", "artists": "The Beatles", "album": "Help!", "year": 1965, "composer": "John Lennon, Paul McCartney", "genre": "Rock", "language": "English"}}

Filename to analyze: "{song_name}"{existing_context}"""
        
        try:
            response = requests.post(
                f"{self.ollama_base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json"
                },
                timeout=30
            )
            
            response.raise_for_status()
            result = response.json()
            
            if "response" not in result:
                logger.error(f"Unexpected response format from Ollama: {result}")
                return {"title": song_name, "error": "Invalid response format"}
            
            # Parse the JSON response
            try:
                metadata_text = result["response"].strip()
                # Sometimes Ollama adds extra text, try to extract just the JSON
                if metadata_text.startswith('{') and metadata_text.endswith('}'):
                    metadata = json.loads(metadata_text)
                else:
                    # Try to find JSON in the response
                    json_match = re.search(r'\{.*\}', metadata_text, re.DOTALL)
                    if json_match:
                        metadata = json.loads(json_match.group())
                    else:
                        raise json.JSONDecodeError("No JSON found", metadata_text, 0)
                
                logger.debug(f"Got metadata for '{song_name}': {metadata}")
                return metadata
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON from Ollama response: {e}")
                logger.error(f"Raw response: {result.get('response', 'No response')}")
                return {"title": song_name, "error": "Failed to parse response"}
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error connecting to Ollama for '{song_name}': {e}")
            return {"error": str(e), "title": song_name}
        except Exception as e:
            logger.error(f"Error getting metadata for '{song_name}': {e}")
            return {"error": str(e), "title": song_name}
    
    def display_metadata_comparison(self, filename, existing, new_metadata, file_type):
        """Display a comparison of existing vs new metadata."""
        print("\n" + "="*80)
        print(f"FILE: {filename} ({file_type})")
        print("="*80)
        
        # Map new metadata keys to display format
        field_mapping = {
            "title": ("Title", existing.get("title", ""), new_metadata.get("title", "")),
            "artists": ("Artist", existing.get("artist", ""), new_metadata.get("artists", "")),
            "album": ("Album", existing.get("album", ""), new_metadata.get("album", "")),
            "year": ("Year", existing.get("year", ""), str(new_metadata.get("year", ""))),
            "composer": ("Composer", existing.get("composer", ""), new_metadata.get("composer", "")),
            "genre": ("Genre", existing.get("genre", ""), new_metadata.get("genre", "")),
            "language": ("Language", existing.get("language", ""), new_metadata.get("language", ""))
        }
        
        changes_found = False
        
        for field, (display_name, old_val, new_val) in field_mapping.items():
            old_val = old_val or "(empty)"
            new_val = new_val or "(empty)"
            
            if old_val != new_val:
                changes_found = True
                print(f"{display_name:12} | OLD: {old_val}")
                print(f"{' '*12} | NEW: {new_val}")
                print("-" * 50)
            else:
                print(f"{display_name:12} | {old_val} (no change)")
        
        # Show comments for MP3 files
        if file_type == "MP3" and existing.get("comments"):
            print(f"{'Comments':12} | {existing['comments']}")
        
        if not changes_found:
            print("\nNO CHANGES DETECTED - All metadata matches existing values")
        else:
            print(f"\nCHANGES DETECTED for {filename}")
        
        print("="*80)

    def confirm_update(self):
        """Ask user for confirmation to proceed with the update."""
        if not self.interactive_mode:
            return True
            
        while True:
            response = input("\nProceed with this update? (y/n/a=yes to all/q=quit): ").lower().strip()
            if response in ['y', 'yes']:
                return True
            elif response in ['n', 'no']:
                return False
            elif response in ['a', 'all']:
                self.interactive_mode = False  # Switch to non-interactive mode
                return True
            elif response in ['q', 'quit']:
                print("Quitting...")
                exit(0)
            else:
                print("Please enter 'y' (yes), 'n' (no), 'a' (yes to all), or 'q' (quit)")

    def get_mp3_existing_metadata(self, file_path):
        """Extract existing metadata from MP3 file."""
        existing = {}
        try:
            audiofile = eyed3.load(str(file_path))
            if audiofile and audiofile.tag:
                existing = {
                    "title": audiofile.tag.title or "",
                    "artist": audiofile.tag.artist or "",
                    "album": audiofile.tag.album or "",
                    "year": str(audiofile.tag.recording_date) if audiofile.tag.recording_date else "",
                    "composer": audiofile.tag.composer or "",
                    "genre": str(audiofile.tag.genre) if audiofile.tag.genre else "",
                    "comments": [str(comment) for comment in audiofile.tag.comments] if audiofile.tag.comments else []
                }
        except Exception as e:
            logger.warning(f"Error reading existing MP3 metadata: {e}")
        return existing

    def update_mp3_metadata(self, file_path, metadata):
        """Update the ID3 tags of an MP3 file with the provided metadata."""
        try:
            # First, get existing metadata
            existing_metadata = self.get_mp3_existing_metadata(file_path)
            
            # Show comparison
            self.display_metadata_comparison(file_path.name, existing_metadata, metadata, "MP3")
            
            # Ask for confirmation
            if not self.confirm_update():
                logger.info(f"Skipping '{file_path.name}' - user declined update")
                self.stats["skipped"] += 1
                return False
            
            output_path = str(self.output_folder / file_path.name)
            source_path = str(file_path)
            
            # Copy the file to the output directory
            logger.info(f"Copying MP3 file to output folder: {output_path}")
            shutil.copy2(source_path, output_path)
            
            # Load the MP3 file
            audiofile = eyed3.load(output_path)
            
            if audiofile is None:
                logger.error(f"Failed to load MP3 file {output_path}")
                return False
            
            # Initialize ID3 tag if it doesn't exist
            if audiofile.tag is None:
                audiofile.initTag(version=(2, 3, 0))
            elif not self.overwrite and (audiofile.tag.title or audiofile.tag.artist):
                logger.info(f"Skipping '{file_path.name}' - already has metadata and overwrite is False")
                self.stats["skipped"] += 1
                return False
                
            # Update the tags with our metadata
            if metadata.get("title"):
                audiofile.tag.title = str(metadata["title"])
                
            if metadata.get("artists"):
                audiofile.tag.artist = str(metadata["artists"])
                    
            if metadata.get("album"):
                audiofile.tag.album = str(metadata["album"])
                
            if metadata.get("year"):
                try:
                    year_val = str(metadata["year"])
                    if year_val.isdigit():
                        audiofile.tag.recording_date = year_val
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid year value '{metadata.get('year')}': {e}")
                
            if metadata.get("composer"):
                audiofile.tag.composer = str(metadata["composer"])
                
            if metadata.get("language"):
                audiofile.tag.comments.set(f"Language: {metadata['language']}")
                
            if metadata.get("genre"):
                try:
                    audiofile.tag.genre = str(metadata["genre"])
                except Exception as e:
                    logger.warning(f"Error setting genre '{metadata.get('genre')}': {e}")
                    audiofile.tag.comments.set(f"Genre: {metadata['genre']}")
            
            # Save the changes
            audiofile.tag.save(output_path)
            logger.info(f"Successfully updated MP3 metadata for '{file_path.name}'")
            return True
            
        except Exception as e:
            logger.error(f"Error updating MP3 metadata for '{file_path.name}': {str(e)}")
            return False

    def get_opus_existing_metadata(self, file_path):
        """Extract existing metadata from Opus file."""
        existing = {}
        try:
            audiofile = OggOpus(str(file_path))
            existing = {
                "title": audiofile.get("TITLE", [""])[0] if audiofile.get("TITLE") else "",
                "artist": audiofile.get("ARTIST", [""])[0] if audiofile.get("ARTIST") else "",
                "album": audiofile.get("ALBUM", [""])[0] if audiofile.get("ALBUM") else "",
                "year": audiofile.get("DATE", [""])[0] if audiofile.get("DATE") else "",
                "composer": audiofile.get("COMPOSER", [""])[0] if audiofile.get("COMPOSER") else "",
                "genre": audiofile.get("GENRE", [""])[0] if audiofile.get("GENRE") else "",
                "language": audiofile.get("LANGUAGE", [""])[0] if audiofile.get("LANGUAGE") else ""
            }
            
            # Debug: Show all available tags
            logger.debug(f"All Opus tags for {file_path.name}: {dict(audiofile)}")
            
        except Exception as e:
            logger.warning(f"Error reading existing Opus metadata: {e}")
        return existing

    def update_opus_metadata(self, file_path, metadata):
        """Update the metadata of an Opus file with the provided metadata."""
        try:
            # First, get existing metadata
            existing_metadata = self.get_opus_existing_metadata(file_path)
            
            # Show comparison
            self.display_metadata_comparison(file_path.name, existing_metadata, metadata, "Opus")
            
            # Ask for confirmation
            if not self.confirm_update():
                logger.info(f"Skipping '{file_path.name}' - user declined update")
                self.stats["skipped"] += 1
                return False
            
            output_path = str(self.output_folder / file_path.name)
            source_path = str(file_path)
            
            # Copy the file to the output directory
            logger.info(f"Copying Opus file to output folder: {output_path}")
            shutil.copy2(source_path, output_path)
            
            # Load the Opus file
            try:
                audiofile = OggOpus(output_path)
            except Exception as e:
                logger.error(f"Failed to load Opus file {output_path}: {e}")
                return False
            
            # Check if we should overwrite existing metadata
            if not self.overwrite and (audiofile.get("TITLE") or audiofile.get("ARTIST")):
                logger.info(f"Skipping '{file_path.name}' - already has metadata and overwrite is False")
                self.stats["skipped"] += 1
                return False
                
            # Update the tags with our metadata
            if metadata.get("title"):
                audiofile["TITLE"] = str(metadata["title"])
                
            if metadata.get("artists"):
                audiofile["ARTIST"] = str(metadata["artists"])
                    
            if metadata.get("album"):
                audiofile["ALBUM"] = str(metadata["album"])
                
            if metadata.get("year"):
                try:
                    year_val = str(metadata["year"])
                    if year_val.isdigit():
                        audiofile["DATE"] = year_val
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid year value '{metadata.get('year')}': {e}")
                
            if metadata.get("composer"):
                audiofile["COMPOSER"] = str(metadata["composer"])
                
            if metadata.get("language"):
                audiofile["LANGUAGE"] = str(metadata["language"])
                
            if metadata.get("genre"):
                audiofile["GENRE"] = str(metadata["genre"])
            
            # Save the changes
            audiofile.save()
            logger.info(f"Successfully updated Opus metadata for '{file_path.name}'")
            return True
            
        except Exception as e:
            logger.error(f"Error updating Opus metadata for '{file_path.name}': {str(e)}")
            return False

    def update_audio_metadata(self, file_path, metadata):
        """Update metadata for either MP3 or Opus files based on file extension."""
        file_extension = file_path.suffix.lower()
        
        if file_extension == ".mp3":
            return self.update_mp3_metadata(file_path, metadata)
        elif file_extension == ".opus":
            return self.update_opus_metadata(file_path, metadata)
        else:
            logger.error(f"Unsupported file format: {file_extension}")
            return False

    def process_files(self):
        """Process all audio files in the input folder."""
        audio_files = self.get_audio_files()
        if not audio_files:
            logger.warning("No audio files found to process.")
            return
            
        logger.info(f"Starting to process {len(audio_files)} files...")
        
        for i, file_path in enumerate(tqdm(audio_files, desc="Processing audio files")):
            try:
                # Extract song name from filename
                song_name = self.clean_filename(file_path.name)
                file_type = file_path.suffix.upper()
                logger.info(f"Processing ({i+1}/{len(audio_files)}) {file_type}: '{song_name}'")
                
                # Get existing metadata first
                if file_path.suffix.lower() == ".mp3":
                    existing_metadata = self.get_mp3_existing_metadata(file_path)
                else:
                    existing_metadata = self.get_opus_existing_metadata(file_path)
                
                # Get metadata from Ollama with context about existing metadata
                metadata = self.get_metadata_from_ollama(song_name, existing_metadata)
                
                # Update audio file with metadata
                success = self.update_audio_metadata(file_path, metadata)
                
                if success:
                    self.stats["success"] += 1
                elif "error" in metadata:
                    logger.error(f"Failed to update metadata: {metadata.get('error')}")
                    self.stats["errors"] += 1
                
                # Update processed count
                self.stats["processed_files"] += 1
                
                # Print batch status
                if (i + 1) % self.batch_size == 0 or i == len(audio_files) - 1:
                    logger.info(f"Progress: {i+1}/{len(audio_files)} files processed.")
                    
                # Delay to avoid overwhelming Ollama
                if i < len(audio_files) - 1:
                    time.sleep(self.rate_limit_delay)
                    
            except Exception as e:
                logger.error(f"Error processing file '{file_path}': {str(e)}")
                self.stats["errors"] += 1
                continue
    
    def print_summary(self):
        """Print a summary of the processing results."""
        logger.info("\n" + "="*50)
        logger.info("PROCESSING SUMMARY")
        logger.info("="*50)
        logger.info(f"Total files found: {self.stats['total_files']}")
        logger.info(f"Files processed: {self.stats['processed_files']}")
        logger.info(f"Successful updates: {self.stats['success']}")
        logger.info(f"Skipped files: {self.stats['skipped']}")
        logger.info(f"Errors: {self.stats['errors']}")
        logger.info("="*50 + "\n")


def main():
    try:
        print("Starting Audio Metadata Generator with Ollama")
        print(f"Input folder: {INPUT_FOLDER}")
        print(f"Output folder: {OUTPUT_FOLDER}")
        print(f"Ollama URL: {OLLAMA_BASE_URL}")
        print(f"Ollama Model: {OLLAMA_MODEL}")
        
        generator = AudioMetadataGenerator()
        generator.process_files()
        generator.print_summary()
        
        print("\nProcess completed! Check metadata_updater.log for details.")
        
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        print(f"Fatal error occurred: {e}")
        return 1
        
    return 0


if __name__ == "__main__":
    exit(main())
