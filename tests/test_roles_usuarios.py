"""Verifica que el vendedor no pueda reactivar ni bloquear manualmente cuentas por fuera del flujo de Órdenes."""
import os,sys,types
# Sólo para prueba aislada de autorización sin conexión PostgreSQL/Kafka:
p=types.ModuleType('psycopg2')
p.IntegrityError=type('IntegrityError',(Exception,),{})
p.connect=lambda *args,**kwargs: None
pex=types.ModuleType('psycopg2.extras')
pex.RealDictCursor=type('RealDictCursor',(),{})
p.extras=pex
sys.modules['psycopg2']=p;sys.modules['psycopg2.extras']=pex
k=types.ModuleType('confluent_kafka')
for name in ['Consumer','KafkaError','KafkaException','TopicPartition']:
 setattr(k,name,type(name,(Exception if name in ('KafkaError','KafkaException') else object,),{}))
ka=types.ModuleType('confluent_kafka.admin')
for name in ['AdminClient','NewTopic']:
 setattr(ka,name,type(name,(),{}))
sys.modules['confluent_kafka']=k;sys.modules['confluent_kafka.admin']=ka
from pathlib import Path
from fastapi.testclient import TestClient
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'services'/'usuarios-service'))
os.environ.setdefault('JWT_SECRET','secret_for_local_backend_tests_32_bytes_xxx')
os.environ.setdefault('INTERNAL_API_KEY','internal_for_local_backend_tests_32_bytes')
import main
main.app.dependency_overrides[main.usuario_actual]=lambda:{'id':51,'nombre':'Vendedor prueba','rol':'vendedor','activo':True}
c=TestClient(main.app)
assert c.patch('/usuarios/123456/estado',json={'activo':False}).status_code==403
assert c.patch('/usuarios/123456/estado',json={'activo':True}).status_code==403
assert c.post('/internal/usuarios/123456/bloquear').status_code==403
main.app.dependency_overrides.clear()
print('PASS usuarios: vendedor no puede cambiar estados directamente, ruta interna requiere clave')
