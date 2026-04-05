import os
import json
import random
import string
import urllib.request
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

WORDS_JSON_PATH = os.path.join(os.path.dirname(__file__), "words.json")

def download_words_if_missing():
    if not os.path.exists(WORDS_JSON_PATH):
        print("Downloading common vocabulary library...")
        try:
            url = "https://raw.githubusercontent.com/first20hours/google-10000-english/master/google-10000-english-no-swears.txt"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            response = urllib.request.urlopen(req)
            text = response.read().decode('utf-8')
            words = text.split('\n')
            
            valid = [w.strip().upper() for w in words if 3 <= len(w.strip()) <= 8]
            selected = valid[:2500] # Grabs 2500 most common English words
            
            with open(WORDS_JSON_PATH, "w", encoding="utf-8") as f:
                json.dump(selected, f, indent=4)
        except Exception as e:
            print("Failed to build words.json:", e)

download_words_if_missing()

def get_word_list():
    try:
        with open(WORDS_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return ["APPLE", "TIGER", "WATER", "LION", "BEAR", "SYSTEM"]

WORD_LIST = get_word_list()

THEMES = {
    "emerald": {
        "bg": (13, 26, 18),
        "board_glow": (50, 180, 100),
        "top_text": (138, 240, 150),
        "cell_fill": (20, 60, 35),
        "cell_shadow": (8, 25, 14),
        "text_col": (190, 255, 190)
    },
    "ocean": {
        "bg": (10, 18, 30),
        "board_glow": (60, 120, 220),
        "top_text": (150, 200, 255),
        "cell_fill": (25, 55, 95),
        "cell_shadow": (10, 22, 45),
        "text_col": (190, 230, 255)
    },
    "sunset": {
        "bg": (30, 15, 15),
        "board_glow": (220, 100, 50),
        "top_text": (255, 180, 120),
        "cell_fill": (90, 40, 30),
        "cell_shadow": (40, 15, 10),
        "text_col": (255, 210, 190)
    },
    "royal": {
        "bg": (20, 10, 25),
        "board_glow": (140, 60, 200),
        "top_text": (220, 150, 255),
        "cell_fill": (65, 30, 90),
        "cell_shadow": (25, 10, 35),
        "text_col": (230, 180, 255)
    },
    "crimson": {
        "bg": (25, 10, 10),
        "board_glow": (200, 50, 60),
        "top_text": (255, 150, 150),
        "cell_fill": (85, 25, 30),
        "cell_shadow": (40, 8, 12),
        "text_col": (255, 190, 190)
    }
}

FONT_PATH = os.path.join(os.path.dirname(__file__), "GameFont.ttf")

def download_font_if_missing():
    if not os.path.exists(FONT_PATH):
        print("Downloading modern Game Font...")
        try:
            url = "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Bold.ttf"
            urllib.request.urlretrieve(url, FONT_PATH)
        except Exception as e:
            print("Failed to download font:", e)


def place_word(word_to_place, grid, size, force_type="any"):
    """
    Tries to place a word thoroughly in the grid by evaluating specific types of directions.
    Supports deep intersection and cross overlaps.
    """
    all_directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
    
    if force_type == "cross":
        directions = [(1, 1), (1, -1)]
    elif force_type == "plus":
        directions = [(0, 1), (1, 0)]
    else:
        directions = all_directions[:]
        
    random.shuffle(directions)
    
    for dr, dc in directions:
        # Retrieve all valid starting positions for this direction mathematically 
        # so we don't 'give up' randomly if the grid is tight.
        valid_starts = []
        for r in range(size):
            for c in range(size):
                end_r = r + (len(word_to_place) - 1) * dr
                end_c = c + (len(word_to_place) - 1) * dc
                if 0 <= end_r < size and 0 <= end_c < size:
                    valid_starts.append((r, c))
                        
        random.shuffle(valid_starts)
        
        for row, col in valid_starts:
            can_place = True
            for i, letter in enumerate(word_to_place):
                curr_r = row + i * dr
                curr_c = col + i * dc
                # Check intersection natively - allowed to overlap deeply!
                if grid[curr_r][curr_c] != '' and grid[curr_r][curr_c] != letter:
                    can_place = False
                    break
                    
            if can_place:
                positions = []
                for i, letter in enumerate(word_to_place):
                    curr_r = row + i * dr
                    curr_c = col + i * dc
                    grid[curr_r][curr_c] = letter
                    positions.append((curr_r, curr_c))
                return positions
                
    return None

def create_new_game_state(word_count=3):
    if word_count <= 3:
        size = 4
    elif word_count <= 5:
        size = 5
    elif word_count <= 8:
        size = 6
    elif word_count <= 11:
        size = 8
    else:
        size = 10
        
    grid = [['' for _ in range(size)] for _ in range(size)]
    words_info = {}
    
    valid_words = [w for w in WORD_LIST if len(w) <= size]
    actual_count = min(word_count, len(valid_words))
    target_words = random.sample(valid_words, actual_count)
    
    UNIQUE_PALETTE = [
        ((250, 80, 80), (150, 40, 40)),   # Red
        ((80, 250, 80), (40, 150, 40)),   # Green
        ((80, 150, 250), (40, 80, 150)),  # Light Blue
        ((250, 80, 250), (150, 40, 150)), # Magenta
        ((250, 200, 50), (150, 120, 30)), # Yellow
        ((50, 200, 250), (20, 120, 150)), # Cyan
        ((250, 130, 50), (150, 70, 20)),  # Orange
        ((150, 50, 250), (80, 20, 150))   # Purple
    ]
    random.shuffle(UNIQUE_PALETTE)
    
    # We guarantee a mixture of Plus (vertical/horizontal) and Cross (diagonals)
    mixture = ["cross", "plus", "cross", "plus", "any", "any", "any", "any"]
    random.shuffle(mixture)
    
    for idx, word in enumerate(target_words):
        force_type = mixture[idx % len(mixture)]
        
        # Try finding a place using the mixed pattern
        positions = place_word(word, grid, size, force_type)
        if not positions:
            # Fallback if forced requirement couldn't be met
            positions = place_word(word, grid, size, "any")
            
        if positions:
            col_idx = idx % len(UNIQUE_PALETTE)
            words_info[word] = {
                "positions": positions,
                "color": UNIQUE_PALETTE[col_idx][0],
                "shadow": UNIQUE_PALETTE[col_idx][1]
            }

    # Fill remaining blanks
    for r in range(size):
        for c in range(size):
            if grid[r][c] == '':
                grid[r][c] = random.choice(string.ascii_uppercase)
                
    theme_name = random.choice(list(THEMES.keys()))
    return grid, words_info, theme_name

def render_grid_image(grid, words_info, found_words, round_num=1, category="RANDOM", theme_name="emerald"):
    download_font_if_missing()
    theme = THEMES.get(theme_name, THEMES["emerald"])
    
    size = len(grid)
    cell_size = 110
    
    margin_side = 50
    margin_top = 160
    margin_bottom = 50
    
    grid_width = size * cell_size + margin_side * 2
    grid_height = size * cell_size + margin_top + margin_bottom

    img = Image.new('RGB', (grid_width, grid_height), color=theme["bg"])
    draw = ImageDraw.Draw(img)

    try:
        font_large = ImageFont.truetype(FONT_PATH, 42)
        font_small = ImageFont.truetype(FONT_PATH, 24)
        font_letter = ImageFont.truetype(FONT_PATH, 65)
    except IOError:
        font_large = font_small = font_letter = ImageFont.load_default()

    # Draw Title
    title_text = f"{category} WORD GRID"
    if hasattr(font_large, 'getbbox'):
        bbox = font_large.getbbox(title_text)
        title_w = bbox[2] - bbox[0]
    else:
        title_w, _ = draw.textsize(title_text, font=font_large)
    draw.text(((grid_width - title_w) / 2, 35), title_text, fill=theme["top_text"], font=font_large)
    
    # Subtitle
    sub_text = f"Round {round_num}  |  {len(words_info)} words  |  Found: {len(found_words)}/{len(words_info)}"
    if hasattr(font_small, 'getbbox'):
        bbox = font_small.getbbox(sub_text)
        sub_w = bbox[2] - bbox[0]
    else:
        sub_w, _ = draw.textsize(sub_text, font=font_small)
    draw.text(((grid_width - sub_w) / 2, 95), sub_text, fill=theme["text_col"], font=font_small)

    # Line Separator
    draw.line([(0, 140), (grid_width, 140)], fill=theme["board_glow"], width=4)
    
    # Outer glowing board enclosure
    rect_pad = 12
    draw.rounded_rectangle(
        [margin_side - rect_pad, margin_top - rect_pad, 
         margin_side + size * cell_size + rect_pad, margin_top + size * cell_size + rect_pad],
        radius=18, outline=theme["board_glow"], width=5
    )

    # Draw Cells
    for row in range(size):
        for col in range(size):
            letter = grid[row][col]
            
            x0 = margin_side + col * cell_size
            y0 = margin_top + row * cell_size
            
            cx0, cy0 = x0 + 6, y0 + 6
            cx1, cy1 = x0 + cell_size - 6, y0 + cell_size - 6
            
            # Default to un-found Theme Colors
            fill_col = theme["cell_fill"]
            shadow_col = theme["cell_shadow"]
            txt_col = theme["text_col"]
            
            # Look up if it's found
            for fw in found_words:
                if (row, col) in words_info[fw]["positions"]:
                    fill_col = words_info[fw]["color"]
                    shadow_col = words_info[fw]["shadow"]
                    txt_col = (255, 255, 255) # Override text to white for found pop
            
            # Huge 3D depth effect:
            draw.rounded_rectangle([cx0+3, cy0+8, cx1+3, cy1+8], radius=15, fill=shadow_col)
            draw.rounded_rectangle([cx0, cy0, cx1, cy1], radius=15, fill=fill_col)
            
            lighter_shade = tuple(min(255, c + 40) for c in fill_col)
            draw.rounded_rectangle([cx0+3, cy0+3, cx1-3, cy1-3], radius=13, outline=lighter_shade, width=2)
            
            # Draw letter
            if hasattr(font_letter, 'getbbox'):
                bbox = font_letter.getbbox(letter)
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1] 
                y_offset = bbox[1] 
            else:
                text_w, text_h = draw.textsize(letter, font=font_letter)
                y_offset = 0
                
            tx = cx0 + ((cx1 - cx0) - text_w) / 2
            ty = cy0 + ((cy1 - cy0) - text_h) / 2 - y_offset
            
            draw.text((tx, ty), letter, fill=txt_col, font=font_letter)

    img_io = BytesIO()
    img.save(img_io, 'PNG')
    img_io.name = "grid.png"
    img_io.seek(0)
    
    return img_io
