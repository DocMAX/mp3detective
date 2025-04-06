import os
import re
import json
import time
import logging
from pathlib import Path
import shutil

import eyed3
from openai import OpenAI
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
API_KEY = "YOUR_OPENAI_API_KEY_HERE"
MODEL = "gpt-4o"
BATCH_SIZE = 10
RATE_LIMIT_DELAY = 1.0
OVERWRITE = True

class MusicMetadataGenerator:
    def __init__(self):
        """
        Initialize the Music MP3 metadata generator with hardcoded values.
        """
        self.input_folder = Path(INPUT_FOLDER)
        self.output_folder = Path(OUTPUT_FOLDER)
        self.model = MODEL
        self.batch_size = BATCH_SIZE
        self.rate_limit_delay = RATE_LIMIT_DELAY
        self.overwrite = OVERWRITE
        
        # Ensure folders exist
        if not self.input_folder.exists():
            raise FileNotFoundError(f"Input folder not found: {self.input_folder}")
        
        if not self.output_folder.exists():
            logger.info(f"Creating output folder: {self.output_folder}")
            self.output_folder.mkdir(parents=True, exist_ok=True)
            
        # Initialize OpenAI client
        try:
            self.client = OpenAI(api_key=API_KEY)
            logger.info(f"Initialized OpenAI client with model: {self.model}")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            raise

        # Statistics for reporting
        self.stats = {
            "total_files": 0,
            "processed_files": 0,
            "success": 0,
            "errors": 0,
            "skipped": 0
        }
        
    def get_mp3_files(self):
        """Find all MP3 files in the input folder."""
        try:
            mp3_files = list(self.input_folder.glob("**/*.mp3"))
            logger.info(f"Found {len(mp3_files)} MP3 files in {self.input_folder}")
            self.stats["total_files"] = len(mp3_files)
            return mp3_files
        except Exception as e:
            logger.error(f"Error finding MP3 files: {e}")
            return []
    
    def clean_filename(self, filename):
        """Extract and clean the song name from the filename."""
        # Remove file extension
        name = os.path.splitext(filename)[0]
        
        # Remove common prefixes, numbering, etc.
        name = re.sub(r'^\d+[\s_\-\.]+', '', name)  # Remove leading numbers with separators
        name = re.sub(r'^\[.*?\][\s_\-\.]*', '', name)  # Remove bracketed text at start
        
        # Replace separators with spaces
        name = re.sub(r'[_\-\.]+', ' ', name)
        
        # Remove extra spaces
        name = re.sub(r'\s+', ' ', name).strip()
        
        return name
    
    def get_metadata_from_gpt(self, song_name):
        """Query GPT-4o to get metadata for a song."""
        prompt = f"""
        I need detailed metadata for the song titled "{song_name}". 
        
        Please provide the following information:
        - Title: The full and correct title of the song
        - Artists: The performers/singers of the song (as a comma-separated string, not an array)
        - Album: The album name or compilation it's from
        - Year: The release year (as a number)
        - Composer: The composer/producer/music director
        - Genre: The primary genre of the song
        - Language: The language of the song's lyrics (if applicable)
        
        Return your response ONLY as a JSON object with these fields. If you're uncertain about any field, provide your best guess but mark it with "confidence": "low". If you cannot determine a field at all, use null for its value.
        
        Example response format:

        Example 1 (English song):
        {{
          "title": "Yesterday",
          "artists": "The Beatles",
          "album": "Help!",
          "year": 1965,
          "composer": "John Lennon, Paul McCartney",
          "genre": "Rock",
          "language": "English"
        }}

        Example 2 (Hindi song):
        {{
          "title": "Tum Hi Ho",
          "artists": "Arijit Singh",
          "album": "Aashiqui 2",
          "year": 2013,
          "composer": "Mithoon",
          "genre": "Indian Pop",
          "language": "Hindi"
        }}
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "You are a music metadata expert with comprehensive knowledge of music across all genres, artists, and time periods. Provide accurate metadata in JSON format ONLY. Do not include any explanations or comments outside the JSON object."},
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Parse the response
            metadata_json = response.choices[0].message.content
            try:
                metadata = json.loads(metadata_json)
                logger.debug(f"Got metadata for '{song_name}': {metadata}")
                return metadata
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON from GPT response: {e}")
                logger.error(f"Raw response: {metadata_json}")
                return {"title": song_name, "error": "Failed to parse response"}
            
        except Exception as e:
            logger.error(f"Error getting metadata for '{song_name}': {e}")
            return {
                "error": str(e),
                "title": song_name
            }
    
    def update_mp3_metadata(self, file_path, metadata):
        """Update the ID3 tags of an MP3 file with the provided metadata."""
        try:
            # Create output path (convert Path to string to avoid issues)
            output_path = str(self.output_folder / file_path.name)
            source_path = str(file_path)
            
            # Copy the file to the output directory
            logger.info(f"Copying file to output folder: {output_path}")
            shutil.copy2(source_path, output_path)
            
            # Load the MP3 file (working with the output path)
            audiofile = eyed3.load(output_path)
            
            # Check if the file was loaded properly
            if audiofile is None:
                logger.error(f"Failed to load MP3 file {output_path}")
                self.stats["errors"] += 1
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
                # Ensure artists is a string, not a list
                if isinstance(metadata["artists"], list):
                    audiofile.tag.artist = ", ".join(str(a) for a in metadata["artists"])
                else:
                    audiofile.tag.artist = str(metadata["artists"])
                    
            if metadata.get("album"):
                audiofile.tag.album = str(metadata["album"])
                
            # Handle year safely
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
                # Use comments for language
                audiofile.tag.comments.set(f"Language: {metadata['language']}")
                
            if metadata.get("genre"):
                # Set genre safely
                try:
                    audiofile.tag.genre = str(metadata["genre"])
                except Exception as e:
                    logger.warning(f"Error setting genre '{metadata.get('genre')}': {e}")
                    # Try setting genre as a comment instead
                    audiofile.tag.comments.set(f"Genre: {metadata['genre']}")
            
            # Save the changes
            audiofile.tag.save(output_path)
            logger.info(f"Successfully updated metadata for '{file_path.name}' saved to {output_path}")
            self.stats["success"] += 1
            return True
            
        except Exception as e:
            logger.error(f"Error updating metadata for '{file_path.name}': {str(e)}")
            self.stats["errors"] += 1
            return False

    def process_files(self):
        """Process all MP3 files in the input folder."""
        mp3_files = self.get_mp3_files()
        if not mp3_files:
            logger.warning("No MP3 files found to process.")
            return
            
        logger.info(f"Starting to process {len(mp3_files)} files...")
        
        for i, file_path in enumerate(tqdm(mp3_files, desc="Processing MP3 files")):
            try:
                # Extract song name from filename
                song_name = self.clean_filename(file_path.name)
                logger.info(f"Processing ({i+1}/{len(mp3_files)}): '{song_name}'")
                
                # Get metadata from GPT
                metadata = self.get_metadata_from_gpt(song_name)
                
                # Update MP3 file with metadata
                success = self.update_mp3_metadata(file_path, metadata)
                
                if not success and "error" in metadata:
                    logger.error(f"Failed to update metadata: {metadata.get('error')}")
                
                # Update processed count regardless of success/failure
                self.stats["processed_files"] += 1
                
                # Print batch status
                if (i + 1) % self.batch_size == 0 or i == len(mp3_files) - 1:
                    logger.info(f"Progress: {i+1}/{len(mp3_files)} files processed.")
                    
                # Delay to avoid rate limiting
                if i < len(mp3_files) - 1:  # No need to delay after the last file
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
        print("Starting Music MP3 Metadata Generator")
        print(f"Input folder: {INPUT_FOLDER}")
        print(f"Output folder: {OUTPUT_FOLDER}")
        
        generator = MusicMetadataGenerator()
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