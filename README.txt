Requirement: Python 3.4 or later

(No library install required)
Library:	Used In:			Purpose:
time		main.py				Timing compression and decompression steps
tracemalloc	main.py				Measuring peak memory usage during coding
csv		main.py				Writing performance metrics to a results CSV file
argparse	main.py				Command-line interface
mimetypes	main.py				Inferring file type (text, image, audio) from extension
collections	huffman.py, arithmetic.py	Building frequency tables (Counter)
heapq		huffman.py			Priority queue for Huffman tree construction
io		huffman.py, arithmetic.py	Efficient byte writing and streaming
typing		huffman.py, arithmetic.py	Type hints and clarity for internal functions and structures

Recommended File Types:
Text	.txt, .csv, .log
Image	.bmp, .pgm
Audio	.wav, .raw
NOTE: Must be uncompressed formats, cannot be compressed formats like .png, .jpeg, or .mp3

To run the program, insert files to compress in data/, then run main.py, receive results in CSV format at ./results/results.csv
To test decompression integrity run --verify (note that decompression is omitted by default due to size complexity)