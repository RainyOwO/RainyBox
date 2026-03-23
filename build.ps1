python -m pip install -r requirements.txt
python -m pip install pyinstaller

if (Test-Path build) { Remove-Item -Recurse -Force build }
if (Test-Path dist) { Remove-Item -Recurse -Force dist }

python -m PyInstaller RainyBox.spec
