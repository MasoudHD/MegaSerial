# Opening `.msproj` files from the command line and Explorer

## Command line

MegaSerial accepts an optional project path:

```text
MegaSerial.exe "C:\Projects\EC200 Test.msproj"
```

From a source checkout:

```bash
python -m MegaSerial "/path/to/EC200 Test.msproj"
```

The path is validated before the window opens. A path that does not exist, is a
directory, or does not end in `.msproj` / `.json` is reported on stderr and the
application exits with status `2` instead of starting. A valid project is loaded
through exactly the same code path as **File > Open**, so behavior cannot drift
between the two, and the window title shows the opened project.

## Windows file association

MegaSerial ships as a portable single-file executable with no installer, so it
**never writes to the registry during normal startup**. Supporting a command-line
argument is not by itself enough for Windows to open `.msproj` files on a
double-click — the association has to be registered once, explicitly.

### Install

Run once, from the location where you keep `MegaSerial.exe`:

```text
MegaSerial.exe --register-file-association
```

This writes per-user entries under `HKEY_CURRENT_USER\Software\Classes`, so it
needs **no administrator rights** and changes nothing for other users:

| Key                                                          | Default value                  |
| ------------------------------------------------------------ | ------------------------------ |
| `Software\Classes\.msproj`                                     | `MegaSerial.Project`           |
| `Software\Classes\MegaSerial.Project`                          | `MegaSerial Project`           |
| `Software\Classes\MegaSerial.Project\DefaultIcon`              | `"<path>\MegaSerial.exe",0`    |
| `Software\Classes\MegaSerial.Project\shell\open\command`       | `"<path>\MegaSerial.exe" "%1"` |

`%1` is quoted, so project paths containing spaces or non-ASCII characters are
passed to MegaSerial as a single argument.

Re-run the command after moving or replacing the executable, because the
registered command stores its full path.

### Remove

```text
MegaSerial.exe --unregister-file-association
```

This deletes the `MegaSerial.Project` key and, only if `.msproj` still points at
MegaSerial, the `.msproj` key as well. An association another application has
since taken over is left untouched.

### Notes

- Both commands print what they did and exit; the GUI does not start.
- On Linux and macOS they report that association is a Windows feature and exit
  with status `1`.
- Windows may show a "how do you want to open this file" prompt the first time;
  the registered entry appears in that list.
