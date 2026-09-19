# Creating & Importing a Sequence CSV

This guide explains how to build a command sequence by hand in a spreadsheet or
text editor and import it into MegaSerial. A *sequence* is a list of steps that
run top-to-bottom; each step sends a payload and then decides when to advance to
the next one.

## 1. The quick version

1. Create a plain-text file that ends in `.csv`.
2. Put this header on the **first line** (this is the full set of columns):

```csv
name,data,fmt,line_ending,enabled,advance,delay_ms,expect,expect_fmt,timeout_ms,on_timeout,max_retries,beep_on_match,fail_on
```

3. Add one row per step.
4. In MegaSerial open the **Sequence** tab and click **Import CSV**, pick your
   file, done. The imported steps *replace* whatever is currently in the table.

A minimal working file:

```csv
name,data,fmt,advance,delay_ms
Reset,AT+RST,ascii,time,1000
Query,AT+VER,ascii,time,1000
```

## 2. Rules you need to know

- **The first row must be the header.** Column matching is by name, so the
  order of columns does not matter and the header is required.
- **You only need the columns you use.** Any column can be omitted; missing
  values fall back to the defaults listed below.
- **Empty cells use the default** for that column. So `delay_ms,,` behaves the
  same as leaving `delay_ms` out.
- **Blank / junk rows are skipped.** A row is ignored unless it has at least one
  of `name`, `data`, or `expect` filled in.
- **Save as UTF-8.** The importer also tolerates a UTF-8 BOM (which is what
  Excel writes), so "CSV UTF-8" from Excel is fine.
- **Quote cells that contain commas.** Standard CSV rules apply — wrap a field in
  double quotes if it contains a comma, e.g. `"AT+CMD=1,2,3"`.

## 3. Column reference

| Column         | Meaning                                          | Allowed values                                             | Default        |
|----------------|--------------------------------------------------|-----------------------------------------------------------|----------------|
| `name`         | Label shown in the step table                    | any text                                                  | `Step`         |
| `data`         | Payload to send                                  | text/hex/binary depending on `fmt`                        | *(empty)*      |
| `fmt`          | How `data` is interpreted                        | `ASCII`, `HEX`, `Binary` (case-insensitive)               | `ASCII`        |
| `line_ending`  | Appended after the payload when sending          | `None`, `LF (\n)`, `CR (\r)`, `CRLF (\r\n)`               | `CRLF (\r\n)`  |
| `enabled`      | Whether the step runs                            | `true` / `false` (`1`, `yes`, `on` also count as true)    | `true`         |
| `advance`      | When to move to the next step                    | `time`, `response`, `both`                                 | `time`         |
| `delay_ms`     | Fixed wait in milliseconds                        | integer                                                    | `1000`         |
| `expect`       | Reply to wait for (used by `response`/`both`)     | text/hex/binary depending on `expect_fmt`                 | *(empty)*      |
| `expect_fmt`   | How `expect` is interpreted                       | `ASCII`, `HEX`, `Binary`                                   | `ASCII`        |
| `timeout_ms`   | How long to wait for `expect`                     | integer                                                    | `2000`         |
| `on_timeout`   | What to do if `expect` never arrives              | `continue`, `stop`, `retry`                                | `continue`     |
| `max_retries`  | Retries when `on_timeout` is `retry`              | integer                                                    | `2`            |
| `beep_on_match`| Play a sound when `expect` is received            | `true` / `false`                                           | `false`        |
| `fail_on`      | Reply that marks the step as failed before `expect` matches | text/hex/binary according to `expect_fmt`            | *(empty)*      |

### How `advance` uses the other columns

- `time` — send `data`, wait `delay_ms`, then continue. `expect` is ignored.
- `response` — send `data`, wait until `expect` is seen (up to `timeout_ms`),
  then continue. On timeout it follows `on_timeout`.
- `both` — wait for `expect`, **then also** wait `delay_ms` before continuing.

When both `expect` and `fail_on` are non-empty for a response-based step,
MegaSerial watches for the failure pattern using `expect_fmt`. If it arrives
before `expect`, the step is marked failed and its configured `on_timeout`
policy determines whether to continue, stop, or retry.

### Formatting the `data` / `expect` cells

The value is parsed according to its format column:

- **ASCII** — plain text. You can use escapes: `\n`, `\r`, `\t`, `\0`, `\\`,
  `\"`, `\'`, and `\xHH` for a raw byte (e.g. `\x02`).
- **HEX** — hex bytes; spaces, commas and `0x` prefixes are allowed and ignored
  (e.g. `48 65`, `0x48,0x65`). Must be an even number of hex digits.
- **Binary** — bits grouped into bytes, e.g. `01001000` (length must be a
  multiple of 8).

> Note: `line_ending` must match one of the labels exactly (including the
> spacing and the `(\n)` part). Any other value results in **no** line ending
> being appended.

## 4. A fuller example

`sequence.csv`:

```csv
name,data,fmt,line_ending,enabled,advance,delay_ms,expect,expect_fmt,timeout_ms,on_timeout,max_retries,beep_on_match,fail_on
Handshake,PING,ascii,CRLF (\r\n),true,response,0,PONG,ascii,1500,retry,3,true,ERROR
Configure,CFG=1,ascii,CRLF (\r\n),true,both,500,ACK,ascii,1500,continue,2,false,
Poll sensor,52 45 41 44,hex,None,true,time,1000,,ascii,2000,continue,2,false,
Disabled step,AT+OFF,ascii,CRLF (\r\n),false,time,1000,,ascii,2000,continue,2,false,
```

What this does:

The Handshake row also treats `ERROR` as a failure response.

1. **Handshake** — send `PING`, wait for `PONG`; if it doesn't arrive within
   1.5 s, retry up to 3 times, and beep when it matches.
2. **Configure** — send `CFG=1`, wait for `ACK`, then wait an extra 500 ms.
3. **Poll sensor** — send the hex bytes `52 45 41 44` (`READ`) with no line
   ending, then wait 1 s.
4. **Disabled step** — present in the table but skipped because `enabled` is
   `false`.

## 5. Importing into MegaSerial

1. Launch the app (`./run.sh` or `python3 -m MegaSerial`).
2. Go to the **Sequence** tab.
3. Click **Import CSV** and choose your file.
4. The steps appear in the table. Reorder with ↑/↓, toggle the **On** checkbox to
   enable/disable steps, then click **▶ Run sequence**.

If nothing imports, check that your rows have a `name`, `data`, or `expect`
value — completely empty rows are ignored on purpose.

## 6. Tip: let the app write the template for you

The fastest way to get a correctly-formatted file is to add one step in the UI,
click **Export CSV**, and open the result in your spreadsheet. It contains the
exact header and value formatting the importer expects, so you can duplicate
rows and edit from there.
