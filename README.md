The Parallel Image Processing System (PIPS) is a Python-based application designed to apply filters and transformations to images using parallel processing for improved performance. By leveraging multiprocessing and multithreading, the system efficiently handles multiple tasks concurrently. It supports dynamic operations such as grayscale conversion, Gaussian blur, and brightness adjustment.

The system features an image registry to manage images and their metadata, a task registry for tracking processing tasks, and a command-line interface (CLI) for seamless interaction. Synchronization mechanisms ensure safe concurrent execution, while processed images are stored and managed effectively.

Full Command Workflow Example
Add Image:
add image1.jpg

Process Image:
process 1 params.json

List Images:
list

Describe Image:
describe 1

Exit:
exit

You can also use the following delete command
delete 1
