from PIL import Image

def add_padding(input_path, output_path, target_size=(128, 128), inner_size=(96, 96)):
    img = Image.open(input_path).convert("RGBA")
    img = img.resize(inner_size, Image.Resampling.LANCZOS)
    
    new_img = Image.new("RGBA", target_size, (0, 0, 0, 0))
    # Center the image
    upper_left_x = (target_size[0] - inner_size[0]) // 2
    upper_left_y = (target_size[1] - inner_size[1]) // 2
    
    new_img.paste(img, (upper_left_x, upper_left_y), img)
    new_img.save(output_path)

if __name__ == "__main__":
    add_padding("extensions/images/icon128.png", "extensions/images/icon128_padded.png")
