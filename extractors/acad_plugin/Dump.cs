using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using Autodesk.AutoCAD.ApplicationServices.Core;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;

[assembly: CommandClass(typeof(Redline.Dump))]

namespace Redline
{
    // A thin dumper: it reads the drawing and writes RawDrawing 1.1 JSON. It decides nothing.
    public class Dump
    {
        List<string> warnings = new();
        List<(string name, string path)> xrefs = new();
        Dictionary<string, int> skipped = new();
        Utf8JsonWriter w = null!;
        long count;

        [CommandMethod("REDLINE_DUMP")]
        public void Run()
        {
            var doc = Application.DocumentManager.MdiActiveDocument;
            var ed = doc.Editor;
            string? tmp = null;
            warnings = new(); xrefs = new(); skipped = new(); count = 0;
            try
            {
                var o = new PromptStringOptions("\nRedline output path: ") { AllowSpaces = true };
                var r = ed.GetString(o);
                if (r.Status != PromptStatus.OK) throw new InvalidOperationException("no output path");
                var outPath = r.StringResult.Trim().Trim('"');
                tmp = outPath + ".part";
                using (var fs = new FileStream(tmp, FileMode.Create, FileAccess.Write))
                using (w = new Utf8JsonWriter(fs))
                    Write(doc.Database);
                File.Move(tmp, outPath, true);
                tmp = null;
                ed.WriteMessage("\nREDLINE_DUMP wrote " + count + " entities\n");
            }
            catch (System.Exception ex)
            {
                try { if (tmp != null) File.Delete(tmp); } catch (System.Exception) { }
                ed.WriteMessage("\nREDLINE_DUMP failed: " + ex.GetType().Name + ": " + ex.Message + "\n");
            }
        }

        void Write(Database db)
        {
            var asm = typeof(Dump).Assembly;
            var acad = asm.GetCustomAttributes<AssemblyMetadataAttribute>().First(a => a.Key == "AcadVersion").Value;
            var file = db.Filename;
            string sha;
            using (var s = new FileStream(file, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
                sha = Convert.ToHexString(SHA256.HashData(s)).ToLowerInvariant();

            w.WriteStartObject();
            w.WriteString("schema_version", "1.1");
            w.WriteString("extractor", "acad_plugin");
            w.WriteString("extractor_version", asm.GetName().Version!.ToString(3));
            w.WriteString("host_version", "AutoCAD " + acad);
            w.WriteString("source_file", Path.GetFileName(file));
            w.WriteString("source_sha256", sha);
            w.WriteString("extracted_at", DateTime.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture));
            w.WriteStartArray("entities");
            var layouts = Walk(db);
            w.WriteEndArray();

            w.WriteStartObject("document");
            w.WriteString("units", db.Insunits.ToString().ToLowerInvariant());
            w.WriteStartArray("layouts");
            foreach (var l in layouts) w.WriteStringValue(l);
            w.WriteEndArray();
            foreach (var kv in skipped) warnings.Add("skipped " + kv.Value + " " + kv.Key);
            foreach (var x in xrefs) warnings.Add("xref not read: " + x.name + " (the plugin path reads no xref content)");
            w.WriteStartArray("xrefs");
            foreach (var x in xrefs)
            {
                w.WriteStartObject();
                w.WriteString("name", x.name);
                w.WriteString("path", x.path);
                w.WriteBoolean("resolved", false);
                w.WriteEndObject();
            }
            w.WriteEndArray();
            w.WriteStartArray("warnings");
            foreach (var m in warnings) w.WriteStringValue(m);
            w.WriteEndArray();
            w.WriteEndObject();
            w.WriteEndObject();
        }

        // Writes the host database entities and returns its layout names. Xrefs are only listed.
        List<string> Walk(Database db)
        {
            var layouts = new List<string>();
            var dependent = 0;
            using var tr = db.TransactionManager.StartOpenCloseTransaction();
            var bt = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
            foreach (ObjectId id in bt)
            {
                var btr = (BlockTableRecord)tr.GetObject(id, OpenMode.ForRead);
                if (btr.IsFromExternalReference || btr.IsFromOverlayReference) { xrefs.Add((btr.Name, btr.PathName)); continue; }
                if (btr.IsDependent) { dependent++; continue; }
                if (btr.IsAnonymous) continue;
                string where;
                if (btr.IsLayout)
                {
                    where = ((Layout)tr.GetObject(btr.LayoutId, OpenMode.ForRead)).LayoutName;
                    layouts.Add(where);
                }
                else where = "block:" + btr.Name;
                foreach (ObjectId eid in btr)
                {
                    try { Emit(tr, (Entity)tr.GetObject(eid, OpenMode.ForRead), where); }
                    catch (System.Exception ex) { warnings.Add("skipped entity " + where + " " + eid.Handle + ": " + ex.GetType().Name + ": " + ex.Message); }
                }
            }
            if (dependent > 0) warnings.Add("xref-dependent block definitions not read: " + dependent);
            return layouts;
        }

        void Emit(Transaction tr, Entity e, string layout)
        {
            string type, text = null!, blockName = null!;
            Point3d? at = null;
            double? rot = null, height = null;
            List<(string, string, bool)>? attrs = null;
            bool? evaluated = null;
            Table? table = null;
            switch (e)
            {
                case AttributeDefinition:
                    return; // template of an attribute, not drawing text; constants are written with the INSERT
                case DBText t:
                    type = "TEXT"; evaluated = !t.HasFields; text = t.TextString; at = t.Position; rot = t.Rotation; height = t.Height; break;
                case MText m:
                    type = "MTEXT"; evaluated = !m.HasFields; text = m.Text; at = m.Location; rot = m.Rotation; height = m.TextHeight; break;
                case Table tb:
                    type = "ACAD_TABLE"; table = tb; at = tb.Position; rot = tb.Rotation; break;
                case BlockReference b:
                    type = "INSERT"; at = b.Position; rot = b.Rotation;
                    var def = (BlockTableRecord)tr.GetObject(b.IsDynamicBlock ? b.DynamicBlockTableRecord : b.BlockTableRecord, OpenMode.ForRead);
                    blockName = def.Name;
                    attrs = new();
                    foreach (ObjectId did in def)
                        if (tr.GetObject(did, OpenMode.ForRead) is AttributeDefinition ad && ad.Constant) attrs.Add((ad.Tag, ad.TextString, !ad.HasFields));
                    foreach (ObjectId aid in b.AttributeCollection)
                    {
                        var a = (AttributeReference)tr.GetObject(aid, OpenMode.ForRead);
                        attrs.Add((a.Tag, a.TextString, !a.HasFields));
                    }
                    break;
                case MLeader ml:
                    type = "MLEADER";
                    if (ml.ContentType == ContentType.MTextContent) { text = ml.MText.Text; at = ml.MText.Location; height = ml.MText.TextHeight; }
                    break;
                case Line ln:
                    type = "LINE"; at = ln.StartPoint; break;
                case Polyline or Polyline2d or Polyline3d:
                    type = "POLYLINE";
                    try { at = ((Curve)e).StartPoint; } catch (System.Exception) { }
                    break;
                default:
                    var tn = e.GetType().Name.ToUpperInvariant();
                    skipped[tn] = skipped.GetValueOrDefault(tn) + 1;
                    return;
            }
            double[]? box = null;
            try
            {
                var x = e.GeometricExtents;
                box = new[] { x.MinPoint.X, x.MinPoint.Y, x.MaxPoint.X, x.MaxPoint.Y };
            }
            catch (System.Exception) { }

            var outer = w;
            using var ms = new MemoryStream();
            using var ew = new Utf8JsonWriter(ms);
            w = ew;
            try
            {
            w.WriteStartObject();
            w.WriteString("id", e.Handle.ToString());
            w.WriteString("type", type);
            w.WriteString("layout", layout);
            w.WriteString("layer", e.Layer);
            w.WriteString("handle", e.Handle.ToString());
            w.WritePropertyName("insertion_point");
            if (at is Point3d p && Finite(p.X, p.Y, p.Z))
            {
                w.WriteStartArray(); w.WriteNumberValue(p.X); w.WriteNumberValue(p.Y); w.WriteNumberValue(p.Z); w.WriteEndArray();
            }
            else w.WriteNullValue();
            w.WritePropertyName("rotation_deg");
            if (rot is double r && Finite(r)) w.WriteNumberValue(r * 180.0 / Math.PI); else w.WriteNullValue();
            w.WritePropertyName("text_height");
            if (height is double h && Finite(h) && h > 0) w.WriteNumberValue(h); else w.WriteNullValue();
            if (evaluated is bool ev) w.WriteBoolean("evaluated", ev);
            w.WriteString("text", text);
            w.WriteString("block_name", blockName);
            w.WritePropertyName("attributes");
            if (attrs == null) w.WriteNullValue();
            else
            {
                w.WriteStartArray();
                foreach (var (tag, value, ok) in attrs)
                {
                    w.WriteStartObject(); w.WriteString("tag", tag); w.WriteString("value", value); w.WriteBoolean("evaluated", ok); w.WriteEndObject();
                }
                w.WriteEndArray();
            }
            w.WritePropertyName("table");
            if (table == null) w.WriteNullValue(); else WriteTable(table);
            w.WriteNull("xref_path");
            w.WritePropertyName("bbox");
            if (box != null && Finite(box) && box[0] <= box[2] && box[1] <= box[3])
            {
                w.WriteStartArray(); foreach (var v in box) w.WriteNumberValue(v); w.WriteEndArray();
            }
            else w.WriteNullValue();
            w.WriteEndObject();
            w.Flush();
            }
            finally { w = outer; }
            outer.WriteRawValue(ms.ToArray());
            count++;
        }

        void WriteTable(Table t)
        {
            w.WriteStartObject();
            w.WriteNumber("rows", t.Rows.Count);
            w.WriteNumber("cols", t.Columns.Count);
            w.WriteStartArray("cells");
            for (var r = 0; r < t.Rows.Count; r++)
                for (var c = 0; c < t.Columns.Count; c++)
                {
                    string s;
                    var ok = true;
                    try { s = t.TextString(r, c, FormatOption.IgnoreMtextFormat); }
                    catch (System.Exception ex)
                    {
                        s = ""; ok = false;
                        warnings.Add("table " + t.Handle + " row " + r + " col " + c + ": cell read failed, " + ex.GetType().Name);
                    }
                    // A field, formula or data link means the text may be a cached value: not evaluated.
                    try
                    {
                        if (ok && !t.GetDataLink(r, c).IsNull) ok = false;
                        var n = t.Cells[r, c].Contents.Count;
                        for (var k = 0; ok && k < n; k++)
                            if (!t.GetFieldId(r, c, k).IsNull || t.HasFormula(r, c, k)) ok = false;
                    }
                    catch (System.Exception) { ok = false; }
                    w.WriteStartObject();
                    w.WriteNumber("r", r);
                    w.WriteNumber("c", c);
                    w.WriteString("text", s ?? "");
                    w.WriteBoolean("evaluated", ok);
                    w.WriteEndObject();
                }
            w.WriteEndArray();
            w.WriteEndObject();
        }

        static bool Finite(params double[] v) => v.All(double.IsFinite);
    }
}
