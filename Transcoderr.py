import argparse
import json
import os
import platform
import re
import subprocess
import sys

os_type = platform.system()
default_handbrake_exe = 'HandBrakeCLI.exe' if os_type == 'Windows' else 'HandBrakeCLI' if os_type == 'Linux' else sys.exit("Error: Unsupported operating system.")
get_bitrate_executable = 'ffmpeg.exe' if os_type == 'Windows' else 'ffmpeg' if os_type == 'Linux' else sys.exit("Error: Unsupported operating system.")
traversed_directories = set()
transcode_queue = set()
transcoded_files = set()
transcode_number = 1
starting_transcode_queue_length = 0

def log_error(file, message):
    with open('brokenfiles.txt', 'a') as f:
        f.write(f'{file}: {message}\n')

def get_duration_ffprobe(file, ffprobe_exe='ffprobe'):
    try:
        result = subprocess.run([ffprobe_exe, '-v', 'quiet', '-print_format', 'json', '-show_streams', '-show_format', file], capture_output=True, text=True, encoding='utf-8')
        media_info = json.loads(result.stdout)
        duration_seconds = float(media_info['format']['duration'])
        duration_hours, remainder = divmod(duration_seconds, 3600)
        duration_minutes, duration_seconds = divmod(remainder, 60)
        return duration_hours, duration_minutes, duration_seconds
    except Exception as e:
        print(f"Error getting duration for file {file}: {e}")
        return None
    
def get_bitrate(file):
    global get_bitrate_executable
    try:
        result = subprocess.run([get_bitrate_executable, '-i', file, '-hide_banner', '-vn'], capture_output=True, text=True, encoding='utf-8', errors='replace', check=True)
        result = result.stderr
    except subprocess.CalledProcessError as e:
        result = e.stderr
    if not result:
        error_message = f"Error: {get_bitrate_executable} is not producing any output for the file {file}. Make sure the ffmpeg executable is installed and the file is a valid media file."
        print(error_message)
        log_error(file, error_message)
        return None
    bitrate_regex = re.compile(r'bitrate: (\d+(\.\d+)?) (k|M)b/s')
    match = bitrate_regex.search(result)
    if match:
        bitrate = float(match.group(1))
        unit = match.group(3)
        if unit == 'M':
            bitrate *= 1000000
        elif unit == 'k':
            bitrate *= 1000
        return int(bitrate)
    else:
        warning_message = f"Warning: {get_bitrate_executable} is not producing any bitrate information for the file {file}. Make sure the ffmpeg executable is installed and the file is a valid media file."
        print(warning_message)
        log_error(file, warning_message)
        return None

def get_output_file(input_file, export_path):
    input_dir = os.path.dirname(input_file)
    input_filename = os.path.splitext(os.path.basename(input_file))[0]
    output_dir = os.path.join(export_path, os.path.relpath(input_dir, args.import_path).replace('\\', os.path.sep))
    output_filename = f"{input_filename}.mkv"
    output_file = os.path.join(output_dir, output_filename)
    if os.path.exists(output_file):
        print(f"{output_file} already exists. Do you want to overwrite that? (y/n/skip)")
        c = input().lower()
        if c == 'overwrite':
            return output_file
        elif c == 'n' or c == 'no':
            file_root, file_ext = os.path.splitext(input_file)
            output_file = f"{file_root}_transcoded{file_ext}"
            return output_file
        elif c == 'skip' or c == 's':
            return 'null'
        else:
            return get_output_file(input_file, export_path)
    else: 
        return output_file

def transcode(input_file, export_path, handbrake_exe, target_bitrate=None, preset_file=None):
    output_file = get_output_file(input_file, export_path)
    if output_file == 'null':
        return
    output_dir = os.path.dirname(output_file)
    global transcode_number
    global transcoded_files
    global starting_transcode_queue_length
    if transcode_number == 1:
        starting_transcode_queue_length = len(transcode_queue)
    os.makedirs(output_dir, exist_ok=True)

    def process_output(output_line):
        encoding_status_pattern = re.compile(
            r'Encoding: task (?P<task_num>\d+) of (?P<total_tasks>\d+), '
            r'(?P<percent>\d+\.\d+) %.*ETA (?P<eta>\d{2}h\d{2}m\d{2}s)'
        )
        match = encoding_status_pattern.search(output_line)
        if match:
            print(f"\rEncoding Task {match.group('task_num')} of {match.group('total_tasks')}."f"Progress: {match.group('percent')}%, ETA: {match.group('eta')}",end='',flush=True,)

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
            '--encoder', 'nvenc_h264',
            '-b', str(target_bitrate * 1024),
            '--cfr',
            '--vfr',
            '--no-detelecine',
            '--no-decomb',
            '--no-deblock',
            '--no-grayscale',
            '--custom-anamorphic',
            '--keep-display-aspect',
            '--preset', 'Very Fast 1080p30',
        ])
    print(f"Transcoding file {transcode_number} of {starting_transcode_queue_length}")
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1, universal_newlines=True) as process:
        for line in process.stdout:
            process_output(line)

    process.wait()
    output_size = os.path.getsize(output_file)
    output_size_mb = int(output_size) / (1024 * 1024)
    print(f"\nFinished encoding {input_file}. Output size: {output_size_mb:.2f} MB")
    transcode_number = transcode_number + 1
    transcoded_files.add(input_file)
    transcode_queue.remove(input_file)

def traverse(root_dir, filter_bitrate, target_bitrate, export_path, handbrake_exe, subfolder_regex, depth=0):
    global traversed_directories
    global transcode_queue
    supported_extensions = [".mp4", ".mkv", ".avi", ".mpg", ".ts", ".mxf", ".gxf", ".lxf", ".wmv", ".flv", ".mov", ".mp3"]
    root_dir = os.path.normpath(root_dir)
    if not os.path.isdir(root_dir):
        print(f"Error: {root_dir} is not a valid directory.")
        sys.exit(1)
    if traversed_directories is None:
        traversed_directories = set()
    full_path = os.path.abspath(root_dir)
    if full_path in traversed_directories:
        print(f"Previously Traversed {root_dir} - Skipping.")
        return
    print(f"Traversing {root_dir}...")
    for item in os.listdir(full_path):
        if item.startswith('.'):
            continue
        item_path = os.path.join(full_path, item)
        if os.path.isdir(item_path):
            if depth > 0 or subfolder_regex is None or re.match(subfolder_regex, item):
                yield from traverse(item_path, filter_bitrate, target_bitrate, export_path, handbrake_exe, subfolder_regex, depth=depth+1)
        elif os.path.isfile(item_path):
            ext = os.path.splitext(item)[1]
            if ext.lower() not in supported_extensions:
                continue
            bitrate = get_bitrate(item_path)
            if bitrate is not None and bitrate > filter_bitrate * 1000000:
                size = os.path.getsize(item_path) / (1024 * 1024)
                duration_hours, duration_minutes, duration_seconds = get_duration_ffprobe(item_path)
                if len(item) > 65 + 5:
                    itemname = item[:65] + '...' + item[-5:]
                else:
                    itemname = item
                print(f"Found: {itemname} ({duration_hours:.0f}h {duration_minutes:.0f}m {duration_seconds:.0f}s, {size:.2f}MB, {bitrate/1000000:.2f} Mbps)\n", end='')
                transcode_queue.add(item_path)
                yield (item_path, bitrate)
    traversed_directories.add(full_path)

def save_transcode_queue():
    global traversed_directories
    global transcoded_files
    global transcode_queue
    file_name = 'transcode_queue.json'
    print("Saving progress...")
    data = {
        "traversed_directories": list(traversed_directories),
        "transcode_queue": list(transcode_queue),
        "transcoded_files": list(transcoded_files),
    }
    with open(file_name, "w+") as file:
        json.dump(data, file)
    print("Progress saved. Exiting...")

def handle_keyboard_interrupt():
    global traversed_directories
    global transcode_queue
    global transcoded_files
    try:
        print(f"\nInterrupt detected. What would you like to do?\nTranscode queue contains {len(transcode_queue)+len(transcoded_files)} item(s).\n1. Save progress and exit\n2. Start transcoding now")
        choice = input("Enter your choice (1 or 2):\n(or 'delete' to reset queues) ")
        if choice == "2":
            print("Starting transcoding...")
            process_transcode_queue(preconfirm = True)
            return
        elif choice == '1':
            save_transcode_queue()
            print()
        elif choice == 'delete':
            os.remove("transcode_queue.json")
            print("Queue has been deleted")
            sys.exit(0)
        else:
            print("Invalid choice. Please try again.")
            handle_keyboard_interrupt()
    except KeyboardInterrupt:
            save_transcode_queue()
            sys.exit(0)

def process_transcode_queue(preconfirm=False):
    global transcode_queue
    global transcoded_files
    total_bitrate = 0
    if not transcode_queue:
        print('No files were found.')
        return False
    for path in transcode_queue:
        bitrate = get_bitrate(path)
        itemname = os.path.basename(path)
        if len(itemname) > 65 + 5:
            itemname = itemname[:65] + '...' + path[-5:]
        else:
            itemname = itemname
        print(f"{itemname} ({bitrate/1000000:.2f} Mbps)")
        if bitrate is not None:
            total_bitrate += bitrate
    total_files = len(transcode_queue)
    average_bitrate = total_bitrate / total_files
    if preconfirm:
        confirm = 'yes'
    else:
        print(f'Found {total_files} file(s) with an average bitrate of {average_bitrate/1000000:.2f} Mbps. Start the transcode queue? ([yes/no/quit/save for later] or [y/n/q/s]) ')
        confirm = input().lower()
    if confirm == 'yes' or confirm == 'y':
        print('Starting transcode process')
        for file in set(transcode_queue):
            output_file = get_output_file(file, args.export_path)
            if output_file == 'null':
                transcode_queue.remove(file)
            else:
                transcode(file, output_file, args.handbrake_exe, target_bitrate=args.target_bitrate)
        print("Transcoding done.")
        os.remove("transcode_queue.json")
        return True
    elif confirm == 'save for later' or confirm == 's':
        save_transcode_queue()
        print('Transcode queue saved for later.')
        return False
    elif confirm == 'quit' or confirm == 'q':
        print('quitting without saving')
        sys.exit(0)
    elif confirm =='n' or confirm =='no':
        return False
    else:
        return process_transcode_queue()

def transcode_queue_found():
    global transcode_queue
    global traversed_directories
    global transcoded_files
    with open("transcode_queue.json", "r") as file:
        data = json.load(file)
        transcode_queue = set(data["transcode_queue"])
        if "traversed_directories" in data:
            traversed_directories = set(data["traversed_directories"])
        else:
            traversed_directories = set()
        if "transcoded_files" in data:
            transcoded_files = set(data["transcoded_files"])
        else: 
            transcoded_files = set()
        if transcode_queue:
            r = process_transcode_queue()
            if r == True:
                print("Transcode Completed Successfully")
            elif r == False:
                return
            else:
                print("uncaught exception")
                sys.exit(0)

def process_complete():
    total_original_size = 0
    total_output_size = 0
    try:    
        for file in transcoded_files:
            original_size = os.path.getsize(file)
            total_original_size += original_size
            output_file = get_output_file(file, args.export_path)
            output_size = os.path.getsize(output_file)
            total_output_size += output_size
        size_difference = total_original_size - total_output_size
        percentage_difference = (size_difference / total_original_size) * 100
        print(f'Done. Total original size: {total_original_size / (1024 * 1024):.2f} MB, total output size: {total_output_size / (1024 * 1024):.2f} MB, size difference: {percentage_difference:.2f}%.')
    except:
        print('done')
        sys.exit(0)

def continue_traversal():
    global transcode_queue
    for file in traverse(args.import_path, args.filter_bitrate, args.target_bitrate, args.export_path, args.handbrake_exe, args.subfolder_regex):
        transcode_queue.add(file[0])
    print("Traversal Complete")
    start_transcoding = process_transcode_queue()
    if start_transcoding:
        return
    else:
        sys.exit(0)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Transcode videos with a bitrate greater than the specified threshold.', add_help=False)
    parser.add_argument('import_path', type=str, help='The path to the directory to import files from.')
    parser.add_argument('-f', '--filter-bitrate', type=int, default=10, help='The minimum bitrate of the files to transcode in Mbps. (default: 10)')
    parser.add_argument('-e', '--export-path', type=str, default=os.getcwd(), help='The path to the directory to export transcoded files to. (default: current working directory)')
    parser.add_argument('-t', '--target-bitrate', type=int, default=5, help='The target bitrate for the transcoded files in Mbps. (default: 5)')
    parser.add_argument('-F', '--flatten', action='store_true', help='Transcoded files will be placed in the export directory without creating a subfolder structure.')
    parser.add_argument('-H', '--handbrake-exe', type=str, default="HandBrakeCLI.exe", help='The path to the HandBrakeCLI executable. (default: "HandBrakeCLI.exe")')
    parser.add_argument('-m', '--ffmpeg-exe', type=str, default=get_bitrate_executable, help='The path to the ffmpeg executable.')
    parser.add_argument('-h', '--help', action='help', default=argparse.SUPPRESS, help='Show this help message and exit.')
    parser.add_argument('-p', '--preset', type=str, help='The path to the HandBrakeCLI preset file. (overrules other quality arguments)')
    parser.add_argument('-s', '--subfolder-regex', type=str, help='Only process subfolders whose names match this regular expression.')
    args = parser.parse_args()

    try:
        if os.path.exists("transcode_queue.json"):
            print(f"previous run found - restoring...")
            transcode_queue_found()
            print("Continuing Traversal...")
        continue_traversal()
    except KeyboardInterrupt:
        handle_keyboard_interrupt()
    process_complete()