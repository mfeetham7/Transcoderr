# Transcoderr
A Python script that traverses a directory for media files and transcodes them with ffmpeg.

## Requirements

* Python 3.x
* ffmpeg

## Installation

1. Install Python 3.x.
2. Install ffmpeg.
3. Clone or download this repository.

## Usage

Run the script by opening a terminal or command prompt and typing:
```
python transcoderr.py "path/to/import" --export "path/to/export"
```

### Arguments

* `import_path` - Required. Path to directory containing media files that need to be transcoded.
* `--export` / `-e` - Optional. Path to directory where transcoded files will be saved. Default is the current working directory.
* `--filter-bitrate` / `-f` - Optional. Minimum bitrate in Mbps. Media files with a bitrate below this will be skipped. Default is `10`.
* `--target-bitrate` / `-t` - Optional. Target bitrate in Mbps. Media files will be transcoded to this bitrate. Default is `5`.
* `--flatten` / `-F` - Optional. Transcoded files will be placed in the export directory without creating a subfolder structure.
* `--handbrake-exe` / `-H` - Optional. Path to HandBrakeCLI executable. Default is `HandBrakeCLI.exe`. (This option is not used in the current implementation and may be removed in future updates)
* `--ffmpeg-exe` / `-m` - Optional. Path to ffmpeg executable. Default is the system's installed ffmpeg executable.
* `--preset` / `-p` - Optional. Path to HandBrakeCLI preset file. (This option is not used in the current implementation and may be removed in future updates)
* `--subfolder-regex` / `-s` - Optional. Regular expression for subfolder name(s) to include in the search. Default is not set, which includes all subfolders.
* `--help` / `-h` - Show the help message and exit.

## Contributing

This is an open-source project, and contributions are welcome. Here are a few guidelines to get you started:

* Fork the project and clone it locally.
* Use feature branches for new features or bug fixes.
* Write clear, concise commit messages.
* Test your changes thoroughly before submitting a pull request.
* Be responsive to feedback and be willing to make changes to your code based on feedback.

## License

This project is licensed under the MIT License - see the `LICENSE` file for details.
