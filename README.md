# MP3Detective

MP3Detective is a powerful tool that automatically updates MP3 file metadata using OpenAI's GPT model. It can identify song details and update ID3 tags for any music genre and language.

## Features

- Automatically identifies song metadata using AI
- Updates MP3 ID3 tags (title, artist, album, year, composer, genre, language)
- Supports multiple languages and music genres
- Preserves original files by creating copies with updated metadata
- Batch processing with progress tracking
- Detailed logging for troubleshooting

## Prerequisites

- Python 3.8 or higher
- Git (for cloning the repository)
- OpenAI API key ([Get one here](https://platform.openai.com/api-keys))

## Quick Start

```bash
# Clone the repository
git clone https://github.com/deepakness/mp3detective.git
cd mp3detective

# Create and activate virtual environment
python -m venv venv

# On Windows
venv\Scripts\activate

# On macOS/Linux
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure OpenAI API key in app.py
# Place MP3 files in input/ directory
# Run the script
python app.py
```

## Detailed Installation

### 1. Clone the Repository

```bash
git clone https://github.com/deepakness/mp3detective.git
cd mp3detective
```

### 2. Choose Installation Method

You can install MP3Detective either in a virtual environment (recommended) or globally.

#### Using Virtual Environment (Recommended)

##### Windows
```bash
# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

##### macOS/Linux
```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

#### Global Installation

##### Windows
```bash
pip install -r requirements.txt
```

##### macOS/Linux
```bash
pip3 install -r requirements.txt
```

## Configuration

1. Open `app.py` in a text editor
2. Replace `YOUR_OPENAI_API_KEY_HERE` with your actual OpenAI API key:
   ```python
   API_KEY = "your-api-key-here"
   ```

## Directory Structure

After cloning, you'll have this structure:
```
mp3detective/
├── .gitignore         # Git ignore rules
├── app.py             # Main application file
├── requirements.txt   # Python dependencies
├── README.md          # This documentation
├── input/             # Place your MP3 files here
└── output/            # Updated files will appear here
```

Note: The `input/` and `output/` directories are kept in Git but their contents are ignored (except for `.gitkeep` files). This means:
- The directories will exist when you clone the repository
- Any files you put in these directories won't be tracked by Git
- Your MP3 files and processed outputs remain local to your machine

## Usage

1. Place your MP3 files in the `input` folder
2. Run the script:

   If using virtual environment (make sure it's activated):
   ```bash
   # Windows
   python app.py

   # macOS/Linux
   python3 app.py
   ```

   If installed globally:
   ```bash
   # Windows
   python app.py

   # macOS/Linux
   python3 app.py
   ```

3. Check the `output` folder for your processed files
4. Review `metadata_updater.log` for detailed processing information

## Configuration Options

You can modify these variables in `app.py`:

- `INPUT_FOLDER`: Directory containing source MP3 files (default: "input")
- `OUTPUT_FOLDER`: Directory for processed files (default: "output")
- `MODEL`: GPT model to use (default: "gpt-4o")
- `BATCH_SIZE`: Number of files to process before showing progress (default: 10)
- `RATE_LIMIT_DELAY`: Delay between API calls in seconds (default: 1.0)
- `OVERWRITE`: Whether to overwrite existing metadata (default: True)

## Troubleshooting

### Common Issues

1. **Git Clone Issues**
   - Ensure you have Git installed
   - Check your internet connection
   - Verify you have the correct repository URL

2. **ModuleNotFoundError**
   - Make sure you've installed dependencies using `pip install -r requirements.txt`
   - Check if you're using the correct Python environment
   - Verify you're in the correct directory

3. **API Key Error**
   - Verify your OpenAI API key is correctly set in `app.py`
   - Ensure your API key has sufficient credits

4. **Permission Errors**
   - Ensure you have write permissions for the `output` directory
   - On Unix-like systems, you might need to use `chmod` to set appropriate permissions

5. **MP3 Loading Errors**
   - Verify your MP3 files aren't corrupted
   - Check if the files are actually MP3 format

### Logs

Check `metadata_updater.log` for detailed error messages and processing information.
Note: The log file is ignored by Git to keep your local logs private.

## Best Practices

1. **Backup Your Files**
   - Always keep backups of your original MP3 files
   - The script creates copies in the output folder, but it's good practice to have backups

2. **API Usage**
   - Monitor your OpenAI API usage to avoid unexpected charges
   - Adjust `RATE_LIMIT_DELAY` if you're hitting rate limits

3. **Large Libraries**
   - For large music libraries, process files in smaller batches
   - Monitor the log file for any issues

4. **Version Control**
   - Don't commit your MP3 files to the repository
   - Don't commit your API key or log files
   - The `.gitignore` file is set up to prevent these from being accidentally committed

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License.

## Acknowledgments

- Uses OpenAI's GPT for metadata identification
- Built with eyeD3 for MP3 tag manipulation
- Progress bars powered by tqdm

## Support

If you encounter any issues or have questions, please:
1. Check the [Issues](https://github.com/deepakness/mp3detective/issues) page
2. Create a new issue if your problem isn't already reported 