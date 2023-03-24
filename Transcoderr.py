import argparse
import json
import os
import platform
import re
import subprocess
import sys
import threading

os_type = platform.system()
default_handbrake_exe = 'HandBrakeCLI.exe' if os_type == 'Windows' else 'HandBrakeCLI' if os_type == 'Linux' else sys.exit("Error: Unsupported operating system.")
get_bitrate_executable = 'ffmpeg.exe' if os_type == 'Windows' else 'ffmpeg' if os_type == 'Linux' else sys.exit("Error: Unsupported operating system.")
traversed_directories = set()
transcode_queue = set()
transcoded_files = set()
transcode_number = 1
starting_transcode_queue_length = 0
preset_file = None

def log_error(file, message):
    with open('brokenfiles.txt', 'a') as f:
        f.write(f'{file}: {message}\n')

def get_duration_ffprobe(file, ffprobe_exe='ffprobe'):
    try:
        result = subprocess.run([ffprobe_exe, '-v', 'quiet', '-print_format', 'json', '-show_streams', '-show_format', file], capture_output=True, text=True, encoding='utf-8')
        media_info = json.loads(result.stdout)
        if 'format' in media_info:
            duration_seconds = float(media_info['format']['duration'])
            duration_hours, remainder = divmod(duration_seconds, 3600)
            duration_minutes, duration_seconds = divmod(remainder, 60)
            return duration_hours, duration_minutes, duration_seconds
        else:
            print(f"\033[33mError getting duration for file \033[36m{file}\033[33m: 'format' key not found in ffprobe output\033[0m")
            return None
    except Exception as e:
        print(f"\033[33mError getting duration for file \033[36m{file}\033[33m: {e}\033[0m")
        return None

def get_bitrate(file):
    global get_bitrate_executable
    try:
        result = subprocess.run([get_bitrate_executable, '-i', file, '-hide_banner', '-vn'], capture_output=True, text=True, encoding='utf-8', errors='replace', check=True)
        result = result.stderr
    except subprocess.CalledProcessError as e:
        result = e.stderr
    if not result:
        error_message = f"\033[33mError: {get_bitrate_executable} is not producing any output for the file {file}. Make sure the ffmpeg executable is installed and the file is a valid media file.\033[0m"
        print(f"\033[31m{error_message}\033[0m")
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
        warning_message = f"\033[33mWarning: {get_bitrate_executable} is not producing any bitrate information for the file {file}. Make sure the ffmpeg executable is installed and the file is a valid media file.\033[0m"
        print(f"\033[33m{warning_message}\033[0m")
        log_error(file, warning_message)
        return None

def get_output_file(input_file, export_path):
    global transcode_number
    base_dir = args.import_path
    input_dir = os.path.dirname(input_file)
    input_filename = os.path.splitext(os.path.basename(input_file))[0]
    output_dir = os.path.join(export_path, os.path.relpath(input_dir, base_dir).replace('\\', os.path.sep))
    output_filename = f"{input_filename}.mkv"
    output_file = os.path.join(output_dir, output_filename)
    if os.path.exists(output_file):
        file_size = os.path.getsize(output_file)
        file_duration = get_duration_ffprobe(output_file)
        if file_size == 0 or file_duration == 0 or file_size == None or file_duration == None:
            print(f"\033[33mOutput file \033[36m{output_file}\033[33m is incomplete (size: {file_size}, duration: {file_duration}). Deleting and re-transcoding.\033[0m")
            os.remove(output_file)
            return output_file
        else:
            print(f"{output_file} already exists. Do you want to overwrite that? [y]es/[n]o/[s]kip")
            timer = threading.Timer(30, c = 'skip')
            timer.start()
            c = input().lower()
            timer.cancel()
            if c == 'overwrite' or c == 'y' or c == 'yes':
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

def transcode(input_file, export_path, target_bitrate=None):
    if export_path == 'null':
        return
    output_dir = os.path.dirname(export_path)
    global transcode_number
    global transcoded_files
    global starting_transcode_queue_length
    global default_handbrake_exe
    global preset_file
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
            print(f"\r\033[32mEncoding Task {match.group('task_num')} of {match.group('total_tasks')}."f"Progress: {match.group('percent')}%, ETA: {match.group('eta')}\033[0m",end='',flush=True,)
    print(f'Transcoding "\033[36m{input_file}\033[0m" to "\033[36m{export_path}\033[0m"...')
    cmd = [
        default_handbrake_exe,
        '-i', input_file,
        '-o', export_path,
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
    output_size = os.path.getsize(export_path)
    output_size_mb = int(output_size) / (1024 * 1024)
    print(f"\nFinished encoding \033[36m{input_file}\033[0m. Output size: {output_size_mb:.2f} MB")
    transcode_number = transcode_number + 1
    transcoded_files.add(input_file)
    transcode_queue.remove(input_file)

def traverse(root_dir, filter_bitrate, target_bitrate, export_path, handbrake_exe, subfolder_regex, depth=0):
    global traversed_directories
    global transcode_queue
    supported_extensions = [".mp4", ".mkv", ".avi", ".mpg", ".ts", ".mxf", ".gxf", ".lxf", ".wmv", ".flv", ".mov", ".mp3"]
    root_dir = os.path.normpath(root_dir)
    if not os.path.isdir(root_dir):
        print(f"Error: \033[36m{root_dir}\033[0m is not a valid directory.")
        sys.exit(1)
    if traversed_directories is None:
        traversed_directories = set()
    full_path = os.path.abspath(root_dir)
    if full_path in traversed_directories:
        print(f"Previously Traversed \033[36m{root_dir}\033[0m - Skipping.")
        return
    print(f"Traversing \033[36m{root_dir}\033[0m...")
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
                print(f"\033[32mFound: {itemname} ({duration_hours:.0f}h {duration_minutes:.0f}m {duration_seconds:.0f}s, {size:.2f}MB, {bitrate/1000000:.2f} Mbps)\n\033[0m", end='')
                transcode_queue.add(item_path)
                yield (item_path, bitrate)
    traversed_directories.add(full_path)

def save_transcode_queue():
    global traversed_directories
    global transcoded_files
    global transcode_queue
    file_name = 'transcode_queue.json'
    print("\033[34mSaving progress...\033[0m")
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
        print(f"\033[33m\nInterrupt detected. What would you like to do?\nTranscode queue contains\033[0m {len(transcode_queue)+len(transcoded_files)}\033[33m item(s).\n1. Save progress and exit\n2. Start transcoding now\033[0m")
        choice = input("Enter your choice (1 or 2):\n(or 'delete' to reset queues) ")
        if choice == "2":
            print("\033[34mStarting transcoding...\033[0m")
            process_transcode_queue(preconfirm = True)
            return
        elif choice == '1':
            save_transcode_queue()
            print()
        elif choice == 'delete':
            os.remove("transcode_queue.json")
            print("\033[33mQueue has been deleted\033[0m")
            sys.exit(0)
        else:
            print("\033[31mInvalid choice. Please try again.\033[0m")
            handle_keyboard_interrupt()
    except KeyboardInterrupt:
            save_transcode_queue()
            sys.exit(0)

def process_transcode_queue(preconfirm=False):
    global transcode_queue
    global transcoded_files
    global default_handbrake_exe
    global preset_file
    total_bitrate = 0
    if not transcode_queue:
        print('\033[33mNo files were found.\033[0m')
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
        print(f'\033[34mFound {total_files} file(s) with an average bitrate of {average_bitrate/1000000:.2f} Mbps. Start the transcode queue? ([yes/no/quit/save for later] or [y/n/q/s]) \033[0m')
        confirm = input().lower()
    if confirm == 'yes' or confirm == 'y':
        print('\033[34mStarting transcode process\033[0m')
        for file in set(transcode_queue):
            o = get_output_file(file, args.export_path)
            if o == 'null':
                print(f"Removing \033[36m{file}\033[0m due to detected corruption.")
                transcode_queue.remove(file)
            else:
                transcode(file, o, target_bitrate=args.target_bitrate)
        print("\033[32mTranscoding done.\033[0m")
        os.remove("transcode_queue.json")
        return True
    elif confirm == 'save for later' or confirm == 's':
        save_transcode_queue()
        print('\033[34mTranscode queue saved for later.\033[0m')
        return False
    elif confirm == 'quit' or confirm == 'q':
        print('\033[33mquitting without saving\033[0m')
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
                print("\033[32mTranscode Completed Successfully\033[0m")
            elif r == False:
                return
            else:
                print("\033[31muncaught exception\033[0m")
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
        print(f'\033[32mDone. Total original size: {total_original_size / (1024 * 1024):.2f} MB, total output size: {total_output_size / (1024 * 1024):.2f} MB, size difference: {percentage_difference:.2f}%.\033[0m')
    except:
        print('\033[32mdone\033[0m')
        sys.exit(0)

def continue_traversal():
    global transcode_queue
    for file in traverse(args.import_path, args.filter_bitrate, args.target_bitrate, args.export_path, args.handbrake_exe, args.subfolder_regex):
        transcode_queue.add(file[0])
    print("\033[34mTraversal Complete\033[0m")
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
    parser.add_argument('-H', '--handbrake-exe', type=str, help='The path to the HandBrakeCLI executable. (default: "HandBrakeCLI.exe")')
    parser.add_argument('-m', '--ffmpeg-exe', type=str, default=get_bitrate_executable, help='The path to the ffmpeg executable.')
    parser.add_argument('-h', '--help', action='help', default=argparse.SUPPRESS, help='Show this help message and exit.')
    parser.add_argument('-p', '--preset', type=str, help='The path to the HandBrakeCLI preset file. (overrules other quality arguments)')
    parser.add_argument('-s', '--subfolder-regex', type=str, help='Only process subfolders whose names match this regular expression.')
    args = parser.parse_args()
    preset_file = args.preset

    try:
        if os.path.exists("transcode_queue.json"):
            print(f"\033[34mprevious run found - restoring...\033[0m")
            transcode_queue_found()
            print("\033[34mContinuing Traversal...\033[0m")
        continue_traversal()
    except KeyboardInterrupt:
        handle_keyboard_interrupt()
    process_complete()
