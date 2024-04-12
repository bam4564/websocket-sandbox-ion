# Setup 

```shell
# Create a new conda environment with Python 3.11
conda create -n websocket-sandbox python=3.11

# Activate the new environment
conda activate websocket-sandbox

# Install dependencies from requirements.txt
pip install -r requirements.txt

# Add your conda environment to Jupyter
python -m ipykernel install --user --name=websocket-sandbox
```

After doing this, open `client.ipynb` and set the kernel to `websocket-sandbox`.