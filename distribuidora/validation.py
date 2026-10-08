import re
from uuid import UUID

MAX_INT = 2_147_483_647
MAX_QTY = 1_000_000
MAX_PRICE = 1_000_000_000
MAX_TOTAL = 9_007_199_254_740_991

class BusinessError(ValueError):
    pass

def integer(value, label='Cantidad', minimum=0, maximum=MAX_QTY):
    if isinstance(value, bool) or not re.fullmatch(r'[0-9]{1,16}', str(value)):
        raise BusinessError(f'{label}: ingresá un número entero.')
    result = int(value)
    if not minimum <= result <= maximum:
        raise BusinessError(f'{label}: debe estar entre {minimum} y {maximum}.')
    return result

def text(value, label, maximum=160, required=True):
    result = str(value or '').strip()
    if (required and not result) or len(result) > maximum:
        raise BusinessError(f'{label}: completá el campo (máximo {maximum} caracteres).')
    return result

def token(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise BusinessError('El formulario venció. Volvé a abrirlo.') from None

def gs(value):
    return 'Gs. ' + f'{int(value or 0):,}'.replace(',', '.')
