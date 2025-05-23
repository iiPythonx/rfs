# iiPythonx / rfs

A remote filesystem for copying files from system to system without SSH or something that requires a lot of setup.

### Running the server

```sh
curl -O https://cdn.iipython.dev/rfs
chmod +x ./rfs
./rfs serve --host 0.0.0.0 --port 8000
```

### Running the client

```sh
curl -O https://cdn.iipython.dev/rfs
chmod +x ./rfs
./rfs connect 10.0.0.1:8000
```
