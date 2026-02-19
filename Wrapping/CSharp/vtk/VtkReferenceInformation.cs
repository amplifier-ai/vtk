// SPDX-FileCopyrightText: Copyright (c) Ken Martin, Will Schroeder, Bill Lorensen
// SPDX-License-Identifier: BSD-3-Clause

using System.Collections.Generic;
using System.Text;

namespace VTK
{
    public class VtkReferenceInformation
    {
        private int freedCount;
        private int keptCount;
        private readonly bool trackClassNames;
        private Dictionary<string, int> classesKept;
        private Dictionary<string, int> classesFreed;

        public VtkReferenceInformation(bool trackClassNames)
        {
            this.trackClassNames = trackClassNames;
            if (trackClassNames)
            {
                classesKept = new Dictionary<string, int>();
                classesFreed = new Dictionary<string, int>();
            }
        }

        public int FreedCount => freedCount;
        public int KeptCount => keptCount;
        public int TotalCount => freedCount + keptCount;

        public void AddFreedObject(string className)
        {
            freedCount++;
            if (trackClassNames && className != null)
            {
                if (classesFreed.ContainsKey(className))
                {
                    classesFreed[className]++;
                }
                else
                {
                    classesFreed[className] = 1;
                }
            }
        }

        public void AddKeptObject(string className)
        {
            keptCount++;
            if (trackClassNames && className != null)
            {
                if (classesKept.ContainsKey(className))
                {
                    classesKept[className]++;
                }
                else
                {
                    classesKept[className] = 1;
                }
            }
        }

        public string ListKeptReferences()
        {
            if (classesKept == null || classesKept.Count == 0)
            {
                return string.Empty;
            }
            var sb = new StringBuilder();
            sb.AppendLine("Classes kept in C# layer:");
            foreach (var kvp in classesKept)
            {
                sb.AppendLine($"  - {kvp.Key}: {kvp.Value}");
            }
            return sb.ToString();
        }

        public string ListFreedReferences()
        {
            if (classesFreed == null || classesFreed.Count == 0)
            {
                return string.Empty;
            }
            var sb = new StringBuilder();
            sb.AppendLine("Classes freed in C# layer:");
            foreach (var kvp in classesFreed)
            {
                sb.AppendLine($"  - {kvp.Key}: {kvp.Value}");
            }
            return sb.ToString();
        }

        public override string ToString()
        {
            return $"VTK GC: freed({freedCount}) - kept({keptCount}) - total({TotalCount})";
        }
    }
}
