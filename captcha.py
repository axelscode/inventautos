import random
import string
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageFilter

def generar_texto_captcha(longitud=5):
    """Genera un texto aleatorio para el CAPTCHA"""
    caracteres = string.ascii_uppercase + string.digits
    return ''.join(random.choice(caracteres) for _ in range(longitud))

def generar_imagen_captcha(texto):
    """Genera una imagen CAPTCHA con el texto dado"""
    # Crear imagen
    ancho = 200
    alto = 60
    imagen = Image.new('RGB', (ancho, alto), color=(255, 255, 255))
    draw = ImageDraw.Draw(imagen)
    
    # Intentar usar una fuente, si no existe usar la predeterminada
    try:
        # Puedes descargar una fuente .ttf o usar la que tengas
        font = ImageFont.truetype("arial.ttf", 30)
    except:
        font = ImageFont.load_default()
    
    # Agregar ruido de fondo (líneas aleatorias)
    for _ in range(5):
        x1 = random.randint(0, ancho)
        y1 = random.randint(0, alto)
        x2 = random.randint(0, ancho)
        y2 = random.randint(0, alto)
        draw.line([(x1, y1), (x2, y2)], fill=(200, 200, 200), width=2)
    
    # Agregar puntos de ruido
    for _ in range(100):
        x = random.randint(0, ancho)
        y = random.randint(0, alto)
        draw.point((x, y), fill=(150, 150, 150))
    
    # Escribir el texto con desplazamiento aleatorio
    x_offset = 20
    for i, char in enumerate(texto):
        # Color aleatorio para cada letra
        color = (
            random.randint(50, 150),
            random.randint(50, 150),
            random.randint(50, 150)
        )
        # Pequeño desplazamiento vertical aleatorio
        y_offset = random.randint(-5, 5)
        draw.text((x_offset + i * 32, 15 + y_offset), char, fill=color, font=font)
    
    # Aplicar un poco de desenfoque (opcional)
    # imagen = imagen.filter(ImageFilter.BLUR)
    
    return imagen