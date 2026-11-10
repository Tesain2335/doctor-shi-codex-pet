"""Load the pinned GUI packages without a breakaway virtualenv executable."""
from pathlib import Path
import site
import sys
app=Path(__file__).resolve().parent
packages=app/'runtime/Lib/site-packages'
sys.path.insert(0,str(packages));site.addsitedir(str(packages))
sys.path.insert(0,str(app))
from companion import main
if __name__=='__main__':main()
