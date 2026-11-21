"""Pruebas de archivo de portada del inventario con almacenamiento temporal."""
from io import BytesIO
from PIL import Image
from fastapi.testclient import TestClient
from app.main import app, current_user
import app.main as main


def test_cargar_imagen_y_permisos(tmp_path):
    main.IMAGE_DIR=tmp_path/'fotos'
    mem=BytesIO()
    Image.new('RGB',(24,24),'navy').save(mem,format='PNG')
    picture=mem.getvalue()
    with TestClient(app) as client:
        app.dependency_overrides[current_user]=lambda:{'id':100,'rol':'cliente'}
        assert client.post('/api/v1/admin/vehiculos/imagen',files={'file':('foto.png',picture,'image/png')}).status_code==403
        app.dependency_overrides[current_user]=lambda:{'id':101,'rol':'admin'}
        bogus=client.post('/api/v1/admin/vehiculos/imagen',files={'file':('x.png',b'<script>','image/png')})
        assert bogus.status_code==422,bogus.text
        result=client.post('/api/v1/admin/vehiculos/imagen',files={'file':('foto.png',picture,'image/png')})
        assert result.status_code==201,result.text
        url=result.json()['imagenUrl']
        assert url.startswith('/uploads/vehicles/') and url.endswith('.webp')
        file=client.get(url)
        assert file.status_code==200 and file.headers['content-type'].startswith('image/webp')
        assert file.content[:4]==b'RIFF'
        assert client.get('/uploads/vehicles/../../etc/passwd').status_code==404
    app.dependency_overrides.clear()
