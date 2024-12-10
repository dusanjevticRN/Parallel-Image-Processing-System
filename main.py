import json
import shutil
import time
from PIL import Image
import numpy as np
from reportlab.rl_settings import imageReaderFlags
from scipy.ndimage import gaussian_filter
import os
import threading
from multiprocessing import Pool, Queue, current_process
from threading import Lock

if not os.path.exists('./processed'):
    os.makedirs('./processed')
if not os.path.exists('./images'):
    os.makedirs('./images')

class ImageRegistry:
    def __init__(self):
        self.images = {}
        self.current_id = 0
        self.lock = Lock()

    def add_image(self, image_path):
        with self.lock:
            self.current_id += 1
            new_image_path = './images/' + os.path.basename(image_path)
            shutil.copy(image_path, new_image_path)
            image_size = os.path.getsize(new_image_path)

            self.images[self.current_id] = {
                'original_image': image_path,
                'image': new_image_path,
                'delete_flag': False,
                'condition': threading.Condition(),
                'filters': [],
                'process_time': None,
                'initial_size': image_size,
                'final_size': None
            }
            print(f"Image added with ID: {self.current_id} at {new_image_path}")
        return self.current_id

    def add_processed_image(self, image_path, original_image):
        with self.lock:
            self.current_id += 1
            processed_image_size = os.path.getsize(image_path)

            self.images[self.current_id] = {
                'original_image': original_image,
                'image': image_path,
                'delete_flag': False,
                'condition': threading.Condition(),
                'filters': [],
                'process_time': None,
                'initial_size': None,
                'final_size': processed_image_size
            }
            print(f"Processed Image added with ID: {self.current_id} at {image_path}")
        return self.current_id

    def mark_for_deletion(self, image_id):
        with self.lock:
            if image_id in self.images:
                self.images[image_id]['delete_flag'] = True
                print(f"Image {image_id} marked for deletion.")

    def remove_image(self, image_id):
        with self.lock:
            if image_id in self.images:
                del self.images[image_id]
                print(f"Image {image_id} removed from registry.")

    def is_marked_for_deletion(self, image_id):
        with self.lock:
            return self.images.get(image_id, {}).get('delete_flag', False)

class TaskRegistry:
    def __init__(self):
        self.tasks = {}
        self.current_task_id = 0
        self.lock = Lock()

    def add_task(self, image_id, transformation_type):
        with self.lock:
            task_id = self.current_task_id
            self.tasks[task_id] = {
                'image_id': image_id,
                'transformation_type': transformation_type,
                'status': 'waiting'
            }
            self.current_task_id += 1
        return task_id

    def update_status(self, task_id, new_status):
        with self.lock:
            if task_id in self.tasks:
                self.tasks[task_id]['status'] = new_status

completed_tasks = Queue()
messages = Queue()
exit_flag = False

def messageHandler():
    while True:
        if exit_flag:
            return

        while not messages.empty():
            print(messages.get_nowait())

class CommandManager:
    def __init__(self, image_registry, task_registry):
        self.image_registry = image_registry
        self.task_registry = task_registry

    def execute_command(self, command, args):
        if command == 'add':
            self.add(args.pop(0))
        elif command == 'process':
            self.process_image(args.pop(0), args.pop(0))
        elif command == 'delete':
            self.delete(args.pop(0))
        elif command == 'list':
            self.list()
        elif command == 'describe':
            self.describe(args.pop(0))
        elif command == 'exit':
            self.exit()

    def add(self, image_path):
        image_id = self.image_registry.add_image(image_path)

    def process_image(self, image_id, json_path):
        image_id = int(image_id)

        if image_id not in self.image_registry.images:
            print(f"Image ID {image_id} not found.")
            return

        if self.image_registry.is_marked_for_deletion(image_id):
            print(f"Image {image_id} is marked for deletion. Skipping processing.")
            return

        with self.image_registry.images[image_id]['condition']:
            print(f"Processing image with ID: {image_id} using multiprocessing...")
            params = load_JSON_file(json_path)
            image_path = self.image_registry.images[image_id]['image']

            transformation_type = params.get('transformation', 'grayscale')
            task_id = self.task_registry.add_task(image_id, transformation_type)
            print(f"Task {task_id} created for Image ID: {image_id} with transformation: {transformation_type}")

            start_time = time.time()
            processed_image_path = f"./processed/processed_image_{self.image_registry.current_id + 1}.jpg"
            run_multiprocessing_task(image_id, image_path, params, processed_image_path)
            end_time = time.time()

            self.image_registry.images[image_id]['process_time'] = end_time - start_time
            self.image_registry.images[image_id]['filters'].append(transformation_type)
            self.image_registry.images[image_id]['final_size'] = os.path.getsize(processed_image_path)

            self.image_registry.add_processed_image(f"./processed/processed_image_{self.image_registry.current_id + 1}.jpg", image_path)

            self.image_registry.images[image_id]['condition'].notify_all()
            print(f"Image {image_id} processing complete.")

        self.task_registry.update_status(task_id, 'completed')
        completed_tasks.put(task_id)

    def delete(self, image_id):
        image_id = int(image_id)
        if image_id in self.image_registry.images:
            with self.image_registry.images[image_id]['condition']:
                self.image_registry.mark_for_deletion(image_id)

                for task_id, task_info in self.task_registry.tasks.items():
                    if task_info['image_id'] == image_id:
                        while self.task_registry.tasks[task_id]['status'] != 'completed':
                            self.image_registry.images[image_id]['condition'].wait()

                image_path = self.image_registry.images[image_id]['image']
                os.remove(image_path)
                self.image_registry.remove_image(image_id)
                print(f"Image {image_id} deleted.")
        else:
            print(f"Image ID {image_id} not found.")

#Ovom metodom ispisujemo sve slike i njihove file pathove
    def list(self):
        print("Listing images:")
        for image_id, image_info in self.image_registry.images.items():
            messages.put(f"Image ID: {image_id}, Path: {image_info['image']}")

#Prikazujemo detalje neke slike
    def describe(self, image_id):
        image_id = int(image_id)
        if self.image_registry.images.get(image_id):
            image_info = self.image_registry.images[image_id]
            flag = False
            while image_info:
                messages.put(f"Image ID: {image_id}")
                messages.put(f"Original Path: {image_info['original_image']}")
                messages.put(f"Current Path: {image_info['image']}")
                messages.put(f"Delete Flag: {image_info['delete_flag']}")
                messages.put(f"Filters Applied: {image_info['filters']}")
                messages.put(f"Processing Time: {image_info['process_time']}")
                messages.put(f"Initial Size: {image_info['initial_size']} bytes")
                messages.put(f"Final Size: {image_info['final_size']} bytes")
                messages.put(f"------------------------------------------------")
                for key, value in self.image_registry.images.items():
                    if value['image'] == image_info['original_image']:
                        image_info = self.image_registry.images[key]
                        flag = True
                if not flag:
                    image_info = None
                flag = False
        else:
            print(f"Image ID {image_id} not found.")

    def exit(self):
        print("Exiting system...")

def load_JSON_file(json_path):
    try:
        with open(json_path) as f:
            params = json.load(f)
        return params
    except Exception as e:
        print(f"Error loading JSON file: {e}")
        return {}

def load_image(image_path):
    try:
        image = Image.open(image_path)
        return np.array(image)
    except Exception as e:
        print(f"Error loading image: {e}")
        return None

def save_image(image_array, path):
    try:
        img = Image.fromarray(image_array)
        img.save(path)
        print(f"Image saved at: {path}")
    except Exception as e:
        print(f"Error saving image: {e}")

def grayscale(image_array):
    return np.mean(image_array[..., :3], axis=2).astype(np.uint8)

def gaussian_blur(image_array, sigma=1):
    red_channel = gaussian_filter(image_array[..., 0], sigma=sigma)
    green_channel = gaussian_filter(image_array[..., 1], sigma=sigma)
    blue_channel = gaussian_filter(image_array[..., 2], sigma=sigma)

    blurred_image = np.zeros_like(image_array)
    blurred_image[..., 0] = red_channel
    blurred_image[..., 1] = green_channel
    blurred_image[..., 2] = blue_channel

    if image_array.shape[-1] == 4:
        alpha_channel = image_array[..., 3]
        blurred_image[..., 3] = alpha_channel

    return np.clip(blurred_image, 0, 255).astype(np.uint8)

def adjust_brightness(image_array, factor=1.0):
    mean_intensity = np.mean(image_array, axis=(0, 1), keepdims=True)
    image_array = (image_array - mean_intensity) * factor + mean_intensity
    return np.clip(image_array, 0, 255).astype(np.uint8)

def run_multiprocessing_task(image_id, image_path, params, processed_image_path):
    #Maksimalni broj procesa je 4, veci broj procesa zapravo ima ovoliko korova, da smo stavili vise procesa, bukvalno bi se borili za mesto sto bi usporqavalo program
    time.sleep(10)
    with Pool(processes=4) as pool: #Pool je dakle kolekcija procesa, ta kolekcija dozvoljava da se vise procesa izvrsava u isto vreme.
        result = pool.apply_async(process_task, args=(image_id, image_path, params, processed_image_path)) #pool.apply_sinc submituje process task poolu za egzekuciju
        result.wait()

def process_task(image_id, image_path, params, processed_image_path):
    print(f"[{current_process().name}] Processing image {image_id}...")
    image_array = load_image(image_path)
    if image_array is None:
        print("Failed to load image. Aborting processing.")
        return

    transformation = params.get('transformation', 'grayscale')
    if transformation == 'grayscale':
        transformed_image = grayscale(image_array)
    elif transformation == 'gaussian_blur':
        sigma = params.get('sigma', 1)
        transformed_image = gaussian_blur(image_array, sigma=sigma)
    elif transformation == 'adjust_brightness':
        factor = params.get('factor', 1.0)
        transformed_image = adjust_brightness(image_array, factor=factor)
    else:
        print(f"Unknown transformation: {transformation}")
        return

    save_image(transformed_image, processed_image_path)

def main():
    image_registry = ImageRegistry()
    task_registry = TaskRegistry()
    command_processor = CommandManager(image_registry, task_registry)
    message_handler = threading.Thread(None, messageHandler) #Kreiramo novi thread za pokretanje messageHandler funkcije
    message_handler.start() #Startujemo taj thread

    while True:
        messages.put('Enter Command: ')
        inp = input().split(" ", 1) #npr ako je komanda add image1.jpg, imacemo dva dela add i image1.jpg
        command = inp.pop(0) #Ekstraktujemo prvi argument i skladistimo ga u command
        if command == 'process': #Ako je komanda process, tu takodje imamo dva argumenta tkd cemo splitovati
            inp = inp[0].split(' ')

        command_processor.execute_command(command, inp)

        if command == 'exit':
            for i in range(0, task_registry.current_task_id):
                while task_registry.tasks[i]['status'] != 'completed':
                    pass

            global exit_flag
            exit_flag = True
            message_handler.join()
            break

if __name__ == "__main__":
    main()
