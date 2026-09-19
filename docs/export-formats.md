# Export formats

This document describes the deterministic file formats MegaSerial writes when
you export data. Sequence CSV import/export is covered separately in
[csv-sequence-guide.md](csv-sequence-guide.md).

## Monitor log

The monitor toolbar offers two exports. Both write the entries currently shown,
so an active regex filter narrows the export in the same way it narrows the view.

- **Save log** writes the rendered monitor text exactly as `View 1` displays it.
- **Export CSV** writes the stored structured events, not the rendered HTML.

### Log CSV

The file is written as UTF-8 **with a BOM** (`utf-8-sig`) so Excel detects the
encoding, and values are quoted by the standard CSV rules. Every event produces
exactly one row. A column that an event does not carry is left empty rather than
filled with a substitute value.

```csv
index,timestamp,elapsed_ms,event_type,direction,data_format,data,text,log_kind,message
```

| Column        | Applies to | Contents                                                          |
| ------------- | ---------- | ----------------------------------------------------------------- |
| `index`       | all        | 1-based position within the export                                 |
| `timestamp`   | all        | `YYYY-MM-DD HH:MM:SS.mmm`, empty if the event has no timestamp     |
| `elapsed_ms`  | all        | Whole milliseconds since the previous timestamped row; empty on the first row |
| `event_type`  | all        | `data` for RX/TX traffic, `log` for application messages           |
| `direction`   | data       | `rx` or `tx`                                                       |
| `data_format` | data       | Always `hex`, naming the encoding used by the `data` column        |
| `data`        | data       | Payload bytes as space-separated uppercase hex, e.g. `4F 4B 0D 0A` |
| `text`        | all        | Readable rendering, with `\` `\r` `\n` `\t` escaped so a row never wraps |
| `log_kind`    | log        | `info`, `warn` or `error`                                          |
| `message`     | log        | The log message, verbatim                                          |

`data` is the lossless representation: it round-trips any byte, including
non-printable and non-UTF-8 payloads. `text` is the convenience rendering and
matches the text the monitor's regex filter runs against — payload bytes decoded
as UTF-8 with replacement characters for invalid sequences, or the log message
for log events.

Exporting never modifies the captured events; it only reads them.

## Graph

The graph toolbar offers **Save image** and **Export CSV**. Both read the data
the graph is currently holding; neither changes live plotting, and an empty
graph is reported instead of writing an empty file.

### Graph image

**Save image** writes a **PNG** of the plot area as displayed: axes, grid,
labels and the currently plotted series. The image is rendered from the plot
itself, so it is not a screenshot of the surrounding window.

### Graph CSV

Written as UTF-8 with a BOM (`utf-8-sig`), one row per plotted point:

```csv
series,point_index,x,y
```

| Column        | Contents                                                        |
| ------------- | --------------------------------------------------------------- |
| `series`      | Series name, as auto-detected from the incoming data             |
| `point_index` | 1-based position within that series, restarting for each series  |
| `x`           | Plotted x value (see below)                                      |
| `y`           | Plotted value                                                    |

This is a **long** format: every series appears as its own block of rows rather
than as its own column. Series are detected independently, so they can have
different lengths and different x values; a wide, shared-x layout would have to
invent values to fill the gaps.

The meaning of `x` follows the graph mode:

- **Time series / Auto** — seconds since the first plotted sample, or the sample
  index when the data carries no timestamp.
- **XY pairs** — the X value parsed from the data.

Numbers are written with Python's default float formatting, which round-trips
exactly, so reading the file back gives the same values that were plotted.
Only points still held by the graph are exported: the **Max pts** setting
discards older samples from the live buffer, and the export reflects that.
