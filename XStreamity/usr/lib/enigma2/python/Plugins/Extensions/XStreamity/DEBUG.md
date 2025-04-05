
# install Python PIP on enigma2
```
opkg update
opkg install python3-ensurepip
python -m ensurepip --upgrade
pip3 install debugpy
```

# use debugpy within /usr/lib/enigma2/python/StartEnigma.py

Add following code snipped to the file (quite at the top, e.g. just below the other import statements)
```
if True: # change to False to turn off debugging feature
    sys.path.append("/usr/lib/enigma2/python") # ensure that enigma python modules are found
    import debugpy

    print("debugpy listening on port 5678 ...")
    debugpy.listen(("0.0.0.0", 5678))  # Set the debug port

    if True: # change to False in order to not wait
        print("Waiting for debugger to attach...")
        debugpy.wait_for_client()  # Pause execution until debugger attaches
        print("Connected")
        debugpy.breakpoint() # manual breakpoint to see directly if it works
```

# Install dependencies for vscode-server on enigma2
```
opkg install libatomic1
```

# setup SSH on your device (optional)

Setup SSH accordingly in order to use a key file. By this you can avoid typing username and password all the time.

On your enigma2:
```
mkdir -p ~/.ssh
```

On your developer machine:
```
ssh-keygen -t rsa -b 4096
scp ~/.ssh/id_rsa root@enigma2:/home/root/.ssh/
```

Add following to your ~/.ssh/config on your developer machine:
```
Host enigma2
    User root
    HostName enigma2
    IdentityFile ~/.ssh/id_rsa
```

On your enigma2:
```
mv /home/root/.ssh/id_rsa /home/root/.ssh/authorized_keys
chmod 600 /home/root/.ssh/authorized_keys
chmod 700 /home/root/.ssh
```

Now you can connect via ssh to your device without any password.
```
ssh enigma2
```

or in your file explorer use following path to access the enigma2 file system:
```
ssh://enigma2
```

# Copy over your Plugin's source code to the enigma2

Copy all the .py files you want to be able to debug.
e.g. copy them via file explorer or scp.
```
scp *.py enigma2:/usr/lib/enigma2/python/Plugins/Extensions/XStreamity
```

Note: You can also remove all .pyc files (via ssh)
```
ssh enigma2 rm -f "/usr/lib/enigma2/python/Plugins/Extensions/XStreamity/*.pyc"
```

# use VSCode for Remote Debugging

Install VSCode in your system (or download the portable version)

Start VSCode and install some extensions:
- Python
- Python Debugging
- Remote SSH

Connect via Remote SSH (icon in left bottom corner) to your enigma2.
A new VSCode window will open where you can open directory `/` or `/usr/lib/enigma2/python/Plugins/Extensions/XStreamity

Create the folder `.vscode` and then file `.vscode/launch.json` (within the opened directory in VSCode) with following content:
```
{
    "version": "0.2.0",
    "configurations": [

        {
            "name": "Python Debugger: Remote Attach",
            "type": "debugpy",
            "request": "attach",
            "connect": {
                "host": "localhost",
                "port": 5678
            },
            "justMyCode": false
        }
    ]
}
```

# Start enigma2 manually

First, comment the enigma2 line under `/etc/inittab`.

Then run following command to apply the changes:
```
init q
```

You will see that enigma2 is not running anymore.


Now start enigma2 manually:
```
enigma2
```

Alternatively use `enigma2.sh` script
```
enigma2.sh
```

You should see now the printed line: `debugpy listening on port 5678 ...`.

# Start debug session

Start a debug session in VSCode with the "Python Debugger: Remote Attach".

If you have enabled `debugpy.wait_for_client()` you will see, that VSCode opens `StartEnigma.py` file and halts on your manually set first breakpoint at line `debugpy.breakpoint()` (respectively next line).

Additionally, you can set a breakpoint in any other line in any .py file within VSCode. The debug session will halt there as soon as the Code is executed.


