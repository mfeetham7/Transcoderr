import argparse
import os
import subprocess
import sys
import configparser
import re
import platform
import json

os_type = platform.system()
default_handbrake_exe = 'HandBrakeCLI.exe' if os_type == 'Windows' else 'HandBrakeCLI' if os_type == 'Linux' else sys.exit("Error: Unsupported operating system.")
default_mediainfo_exe = 'mediainfo'
config = configparser.ConfigParser()
config.read('config.ini')
traversed_files = set()
transcode_queue = set()

def log_error(file, message):
    with open('brokenfiles.txt', 'a') as f:
        f.write(f'{file}: {message}\n')

def get_bitrate(file, mediainfo_exe):
    try:
        result = subprocess.run([mediainfo_exe, file], capture_output=True, text=True, check=True, encoding='utf-8')
        if not result.stdout:
            error_message = f"Error: {mediainfo_exe} is not producing any output for the file {file}. Make sure the mediainfo executable is installed and the file is a valid media file."
            print(error_message)
            log_error(file, error_message)
            return None
        for line in result.stdout.split('\n'):
            if line.startswith('Bit rate') or line.startswith('Nominal bit rate') or line.startswith('Overall bit rate'):
                bitrate_str = line.split(':')[1].strip().replace(' kb/s', '').replace(' Mb/s', '').replace(' ', '.')
                if bitrate_str == 'Constant' or bitrate_str == 'Variable':
                    return None
                bitrate = float(bitrate_str)
                if 'Mb' in line:
                    bitrate *= 1000000
                elif 'kb' in line:
                    bitrate *= 1000
                return int(bitrate)
        warning_message = f"Warning: {mediainfo_exe} is not producing any bitrate information for the file {file}. Make sure the mediainfo executable is installed and the file is a valid media file."
        print(warning_message)
        log_error(file, warning_message)
        bitrate = 0
        return bitrate
    except subprocess.CalledProcessError as e:
        error_message = f"Error: {mediainfo_exe} is not producing any output for the file {file}. Make sure the mediainfo executable is installed and the file is a valid media file."
        print(error_message)
        log_error(file, error_message)
        bitrate = 0
        return bitrate

def get_output_file(input_file, export_path):
    input_dir = os.path.dirname(input_file)
    input_filename = os.path.splitext(os.path.basename(input_file))[0]
    output_dir = os.path.join(export_path, os.path.relpath(input_dir, args.import_path).replace('\\', os.path.sep))
    output_filename = f"{input_filename}.mkv"
    output_file = os.path.join(output_dir, output_filename)
    return output_file

def transcode(input_file, export_path, handbrake_exe, target_bitrate=None, preset_file=None):
    output_file = get_output_file(input_file, export_path)
    # Get the directory path of the output file and create the folder structure if it doesn't exist
    output_dir = os.path.dirname(output_file)
    os.makedirs(output_dir, exist_ok=True)

    def process_output(output_line):
        encoding_status_pattern = re.compile(r'Encoding:.*\s(?P<fps>\d+\.\d+)\s(?P<unit>fps)')
        match = encoding_status_pattern.search(output_line)
        if match:
            # Print the status
            print(f"\rEncoding file {input_file}. Average fps: {match.group('fps')} {match.group('unit')}", end='')

    print(f'Transcoding "{input_file}" to "{output_file}"...')
    cmd = [
        handbrake_exe,
        '-i', input_file,
        '-o', output_file,
        '--all-audio',
        '--audio-lang-list', 'all',
        '--all-subtitles',
        '--subtitle-lang-list', 'all',
    ]

    if preset_file:
        cmd.extend(['--preset-import-file', preset_file])
    else:
        cmd.extend([
            '--encoder', 'nvenc_h264',  # or '--encoder', 'nvenc_hevc'
            '-b', str(target_bitrate * 1024),
            '--cfr',
            '--vfr',
            '--no-detelecine',
            '--no-decomb',
            '--no-deblock',
            '--no-grayscale',
            '--custom-anamorphic',
            '--keep-display-aspect',
            '--preset', 'Very Fast 1080p30',  # or other preset that suits your needs
        ])

    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=1, universal_newlines=True) as process:
        for line in process.stdout:
            process_output(line)

        # Print HandbrakeCLI output and errors
        print("Handbrake Output:")
        print(process.stdout.read())
        print("Handbrake Errors:")
        print(process.stderr.read())

    # Wait for the process to complete before getting the file size
    process.wait()
    output_size = os.path.getsize(output_file)  # Move this line here
    print("\n")

def traverse(root_dir, filter_bitrate, target_bitrate, export_path, handbrake_exe, mediainfo_exe, subfolder_regex, depth=0):
    supported_extensions = [".mp4", ".mkv", ".avi", ".mpg", ".ts", ".mxf", ".gxf", ".lxf", ".wmv", ".flv", ".mov", ".mp3"]
    print(f"Traversing {root_dir}...")
    global traversed_files
    global transcode_queue
    root_dir = os.path.normpath(root_dir)
    if not os.path.isdir(root_dir):
        print(f"Error: {root_dir} is not a valid directory.")
        sys.exit(1)
    if traversed_files is None:
        traversed_files = set()
    for file in os.listdir(root_dir):
        if file.startswith('.'):
            continue
        if os.path.isfile(os.path.join(root_dir, file)):
            ext = os.path.splitext(file)[1]
            if ext.lower() not in supported_extensions:
                continue
            path = os.path.join(root_dir, file)
            if path in traversed_files:
                #print(f"{path} already traversed, skipping")
                continue
            traversed_files.add(path)
            #print(f"{path} added to traversed_files")
            #print(traversed_files)
            bitrate = get_bitrate(path, mediainfo_exe)
            if bitrate is not None and bitrate > filter_bitrate * 1000000:
                size = os.path.getsize(path) / (1024 * 1024)
                duration = subprocess.check_output([mediainfo_exe, '--Inform=General;%Duration%', path], encoding='utf-8')
                duration_seconds = int(duration.strip()) / 1000
                duration_minutes, duration_seconds = divmod(duration_seconds, 60)
                duration_hours, duration_minutes = divmod(duration_minutes, 60)
                print(f"{file} ({duration_hours:.0f}h {duration_minutes:.0f}m {duration_seconds:.0f}s, {size:.2f}MB, {bitrate/1000000:.2f} Mbps)", end='')
                transcode_queue.add(path)
                yield (path, bitrate)
        elif os.path.isdir(os.path.join(root_dir, file)):
            if depth > 0 or subfolder_regex is None or re.match(subfolder_regex, file):
                subfolder = os.path.join(root_dir, file)
                for subfile in traverse(subfolder, filter_bitrate, target_bitrate, export_path, handbrake_exe, mediainfo_exe, subfolder_regex, depth=depth+1):
                    yield subfile

def save_transcode_queue(files):
    data = {
        "transcode_queue": [path for path, bitrate in files]
    }
    with open("transcode_queue.json", "w") as file:
        json.dump(data, file)

def process_transcode_queue(files):
    if not files:
        print('No files were found.')
        return False

    total_files = len(files)
    total_bitrate = sum(bitrate for _, bitrate in files)
    average_bitrate = total_bitrate / total_files

    print(f'Found {total_files} file(s) with an average bitrate of {average_bitrate/1000000:.2f} Mbps. Start the transcode queue? ([yes/no/quit/save for later] or [y/n/q/s]) ')
    confirm = input().lower()
    if confirm == 'yes' or confirm == 'y':
        print('Starting transcode process')
        return True
    elif confirm == 'save for later' or confirm == 's':
        save_transcode_queue(files)
        print('Transcode queue saved for later.')
        return False
    elif confirm == 'quit' or confirm == 'q':
        print('quitting without saving')
        return False
    else:
        print('Aborted.')
        return False

def handle_keyboard_interrupt():
    global traversed_files
    global transcode_queue
    print("\nInterrupt detected. What would you like to do?")
    print(f"Transcode queue contains {len(transcode_queue)} item(s).")
    print("1. Save progress and exit")
    print("2. Start transcoding now")
    choice = input("Enter your choice (1 or 2): ")
    if choice == "1":
        print("Saving progress...")
        data = {
            "traversed_files": list(traversed_files),
            "transcode_queue": list(transcode_queue),
        }
        with open("transcode_queue.json", "w") as file:
            json.dump(data, file)
        print("Progress saved. Exiting...")
        sys.exit(0)
    elif choice == "2":
        print("Starting transcoding...")
        return
    else:
        print("Invalid choice. Please try again.")
        handle_keyboard_interrupt()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Transcode videos with a bitrate greater than the specified threshold.', add_help=False)
    parser.add_argument('import_path', type=str, help='The path to the directory to import files from.')
    parser.add_argument('-f', '--filter-bitrate', type=int, help='The minimum bitrate of the files to transcode in Mbps. (default: 10)')
    parser.add_argument('-e', '--export-path', type=str, help='The path to the directory to export transcoded files to. (default: current working directory)')
    parser.add_argument('-t', '--target-bitrate', type=int, help='The target bitrate for the transcoded files in Mbps. (default: 5)')
    parser.add_argument('-F', '--flatten', action='store_true', help='Transcoded files will be placed in the export directory without creating a subfolder structure.')
    parser.add_argument('-H', '--handbrake-exe', type=str, help='The path to the HandBrakeCLI executable. (default: "HandBrakeCLI.exe")')
    parser.add_argument('-m', '--mediainfo-exe', type=str, help='The path to the mediainfo executable. (default: "mediainfo")')
    parser.add_argument('-h', '--help', action='help', default=argparse.SUPPRESS, help='Show this help message and exit.')
    parser.add_argument('-p', '--preset', type=str, help='The path to the HandBrakeCLI preset file. (overrules other quality arguments)')
    parser.add_argument('-s', '--subfolder-regex', type=str, help='Only process subfolders whose names match this regular expression.')

    args = parser.parse_args()
    args.filter_bitrate = config.getint('DEFAULT', 'filter_bitrate', fallback=10) if args.filter_bitrate is None else args.filter_bitrate
    args.target_bitrate = config.getint('DEFAULT', 'target_bitrate', fallback=5) if args.target_bitrate is None else args.target_bitrate
    args.export_path = config.get('DEFAULT', 'export_path', fallback=os.getcwd()) if args.export_path is None else args.export_path
    args.handbrake_exe = config.get('DEFAULT', 'handbrake_exe', fallback=default_handbrake_exe) if args.handbrake_exe is None else args.handbrake_exe
    args.mediainfo_exe = config.get('DEFAULT', 'mediainfo_exe', fallback=default_mediainfo_exe) if args.mediainfo_exe is None else args.mediainfo_exe
    config['DEFAULT'].update({k: str(v) for k, v in vars(args).items()})

    try:
        files = []
        traversed_files = set()
        transcode_queue = set()

        # Check if the transcode_queue.json file exists
        if os.path.exists("transcode_queue.json"):

            # Load the data from the JSON file
            with open("transcode_queue.json", "r") as file:
                data = json.load(file)
                transcode_queue = set(data["transcode_queue"])
                if traversed_files:
                    traversed_files = set(data["traversed_files"])

                # Check if there are files in the transcode queue
                if transcode_queue:

                    # Print the files in the transcode queue
                    print("Found files in transcode queue:")
                    for path in transcode_queue:
                        bitrate = get_bitrate(path, args.mediainfo_exe)
                        print(f"{path} ({bitrate/1000000:.2f} Mbps)")

                    # Prompt user to transcode files in the queue
                    print("Do you want to transcode these files now? ([yes/no/quit/save for later] or [y/n/q/s])")
                    confirm = input().lower()

                    # If the user confirms, process the transcode queue and transcode the files
                    if confirm == "yes" or confirm == "y":
                        files = [(path, get_bitrate(path, args.mediainfo_exe)) for path in transcode_queue]
                        start_transcoding = process_transcode_queue(files)
                        if start_transcoding:
                            for file, _ in files:
                                transcode(file, args.export_path, args.handbrake_exe, target_bitrate=args.target_bitrate)
                            # Print the completion message and remove the transcode_queue.json file
                            print("Transcoding done.")
                            os.remove("transcode_queue.json")
                        else:
                            sys.exit(0)
                        for file, _ in files:
                            transcode(file, args.export_path, args.handbrake_exe, target_bitrate=args.target_bitrate)

                        # Print the completion message and remove the transcode_queue.json file
                        print("Transcoding done.")
                        os.remove("transcode_queue.json")
                    elif confirm == "q" or confirm == "quit":
                        sys.exit(0)
                    elif confirm == "save for later" or confirm == 's':
                        save_transcode_queue(files)
                        print('Transcode queue saved for later.')
                        sys.exit(0)
                    # If the user does not confirm, traverse the import path and process the transcode queue
                    else:
                        for file in traverse(args.import_path, args.filter_bitrate, args.target_bitrate, args.export_path, args.handbrake_exe, args.mediainfo_exe, args.subfolder_regex):
                            files.append(file)
                        start_transcoding = process_transcode_queue(files)
                        if start_transcoding:
                            for file, _ in files:
                                transcode(file, args.export_path, args.handbrake_exe, target_bitrate=args.target_bitrate)
                            # Print the completion message and remove the transcode_queue.json file
                            print("Transcoding done.")
                            os.remove("transcode_queue.json")
                        else:
                            sys.exit(0)

                # If there are no files in the transcode queue, restore the list of traversed files and process the transcode queue
                else:
                    print("Restoring list of traversed files...")
                    for file in traverse(args.import_path, args.filter_bitrate, args.target_bitrate, args.export_path, args.handbrake_exe, args.mediainfo_exe, args.subfolder_regex):
                        files.append(file)
                        start_transcoding = process_transcode_queue(files)
                        if start_transcoding:
                            for file, _ in files:
                                transcode(file, args.export_path, args.handbrake_exe, target_bitrate=args.target_bitrate)
                            # Print the completion message and remove the transcode_queue.json file
                            print("Transcoding done.")
                            os.remove("transcode_queue.json")
                        else:
                            sys.exit(0)

        # If the transcode_queue.json file does not exist, traverse the import path and process the transcode queue
        else:
            for file in traverse(args.import_path, args.filter_bitrate, args.target_bitrate, args.export_path, args.handbrake_exe, args.mediainfo_exe, args.subfolder_regex):
                files.append(file)
            start_transcoding = process_transcode_queue(files)
            if start_transcoding:
                for file, _ in files:
                    transcode(file, args.export_path, args.handbrake_exe, target_bitrate=args.target_bitrate)
                # Print the completion message and remove the transcode_queue.json file
                print("Transcoding done.")
                os.remove("transcode_queue.json")
            else:
                sys.exit(0)

        # Use the configuration data from the config.ini file
        with open('config.ini', 'w') as f:
            config.write(f)
            
    #Handle KeyboardInterrupt to gracefully exit the script
    except KeyboardInterrupt:
        handle_keyboard_interrupt()

    total_files = len(files)
    total_bitrate = sum(bitrate for _, bitrate in files)
    average_bitrate = total_bitrate / total_files

    print(f'Found {total_files} file(s) with an average bitrate of {average_bitrate/1000000:.2f} Mbps. Start the transcode queue? (yes/no) ')
    confirm = input()
    if confirm.lower() != 'yes':
        print('Aborted.')
        sys.exit(0)

    total_original_size = 0
    total_output_size = 0

    for file, bitrate in files:
        original_size = os.path.getsize(file)
        total_original_size += original_size

        if args.preset:
            transcode(file, args.export_path, args.handbrake_exe, preset_file=args.preset)
        else:
            transcode(file, args.export_path, args.handbrake_exe, target_bitrate=args.target_bitrate)

        output_file = get_output_file(file, args.export_path)
        output_size = os.path.getsize(output_file)
        total_output_size += output_size
        traversed_files.add(file)
    size_difference = total_original_size - total_output_size
    percentage_difference = (size_difference / total_original_size) * 100

    print(f'Done. Total original size: {total_original_size / (1024 * 1024):.2f} MB, total output size: {total_output_size / (1024 * 1024):.2f} MB, size difference: {percentage_difference:.2f}%.')
    print('done')