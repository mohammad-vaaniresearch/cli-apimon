# Publishing apimon to PyPI

Follow these steps to build and publish the `apimon` package.

## 1. Prerequisites

- A [PyPI](https://pypi.org/) account.
- `build` and `twine` installed:
  ```bash
  pip install build twine
  ```

## 2. Update Version

Ensure the version in `apimon/__init__.py` (or wherever it's defined) matches your intended release version.

## 3. Build the Package

From the root directory of the project:
```bash
python3 -m build
```
This will create a `dist/` directory with `.tar.gz` and `.whl` files.

## 4. Upload to TestPyPI (Optional but Recommended)

It's good practice to test the upload on TestPyPI first:
```bash
python3 -m twine upload --repository testpypi dist/*
```

## 5. Upload to PyPI

Finally, upload the package to the official PyPI:
```bash
python3 -m twine upload dist/*
```

## 6. Include Frontend Assets

The `apimon` tool includes a React/Ink UI that requires Node.js. Currently, the `apimon ui` command attempts to run `npm start` in the `frontend` directory. 

For a production pip package, you should consider:
- Bundling the compiled JS in the package using `tool.setuptools.package-data`.
- Or, documenting that users need to have `node` and `npm` installed and run `npm install` in the frontend directory (as the current implementation does).

---

### Current Packaging Configuration
In `pyproject.toml`:
```toml
[tool.setuptools.packages.find]
where = ["."]
include = ["apimon*"]

[tool.setuptools.package-data]
apimon = ["py.typed"]
```
To include the frontend, you might need to add:
```toml
[tool.setuptools.package-data]
apimon = ["py.typed"]
"*" = ["frontend/**/*"]
```
*(Note: Ensure `.gitignore` doesn't exclude needed files during build)*
