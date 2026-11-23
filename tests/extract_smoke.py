import tempfile, zipfile
from pathlib import Path
from PySide6.QtCore import QCoreApplication
from neon.extract import ExtractWorker
app=QCoreApplication([])
with tempfile.TemporaryDirectory() as t:
    root=Path(t); z=root/'good.zip'
    with zipfile.ZipFile(z,'w') as f: f.writestr('folder/file.txt','hello')
    results=[]; worker=ExtractWorker(z); worker.result.connect(lambda path,error: results.append((path,error))); worker.run()
    assert results[0][0] and (Path(results[0][0])/'folder/file.txt').read_text()=='hello'
    z=root/'bad.zip'
    with zipfile.ZipFile(z,'w') as f: f.writestr('../escape.txt','bad')
    results=[]; worker=ExtractWorker(z); worker.result.connect(lambda path,error: results.append((path,error))); worker.run()
    assert not results[0][0] and results[0][1] and not (root/'escape.txt').exists()
print('ZIP extraction and path traversal rejection: PASS')
