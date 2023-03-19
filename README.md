# Transcoderr
A Python script that traverses a directory for media files and transcodes them with HandbrakeCLI.

## Requirements

* Python 3.x
* HandbrakeCLI (download at [https://handbrake.fr/downloads2.php](https://handbrake.fr/downloads2.php))
* mediainfo (download at [https://mediaarea.net/en/MediaInfo/Download](https://mediaarea.net/en/MediaInfo/Download))
* (Optional) A Handbrake preset file for transcoding

## Installation

1. Install Python 3.x.
2. Install HandbrakeCLI and mediainfo.
3. Clone or download this repository.
4. (Optional) Place your Handbrake preset file in the same directory as the script.

## Usage

Run the script by opening a terminal or command prompt and typing:
```
python transcoder.py --import "path/to/import" --export "path/to/export"
```

### Arguments

* `--import` / `-i` - Required. Path to directory containing media files that need to be transcoded.
* `--export` / `-e` - Required. Path to directory where transcoded files will be saved.
* `--handbrake_exe` / `-h` - Optional. Path to HandbrakeCLI executable. Default is `HandBrakeCLI.exe` on Windows, and `HandBrakeCLI` on Linux and macOS.
* `--mediainfo_exe` / `-m` - Optional. Path to mediainfo executable. Default is `mediainfo` on Linux and macOS, and `mediainfo.exe` on Windows.
* `--filter_bitrate` / `-f` - Optional. Minimum bitrate in Mbps. Media files with a bitrate below this will be skipped. Default is `0`.
* `--target_bitrate` / `-t` - Optional. Target bitrate in Mbps. Media files will be transcoded to this bitrate if a preset file is not specified. Default is `10`.
* `--preset` / `-p` - Optional. Path to Handbrake preset file. If specified, the target bitrate will be ignored.
* `--subfolder_regex` / `-s` - Optional. Regular expression for subfolder name(s) to include in the search. Default is `.*`, which includes all subfolders.

## Contributing

This is an open-source project, and contributions are welcome. Here are a few guidelines to get you started:

* Fork the project and clone it locally.
* Use feature branches for new features or bug fixes.
* Write clear, concise commit messages.
* Test your changes thoroughly before submitting a pull request.
* Be responsive to feedback and be willing to make changes to your code based on feedback.

## License

This project is licensed under the MIT License - see the `LICENSE` file for details.
