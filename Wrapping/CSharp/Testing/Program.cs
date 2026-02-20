// SPDX-FileCopyrightText: Copyright (c) Ken Martin, Will Schroeder, Bill Lorensen
// SPDX-License-Identifier: BSD-3-Clause

// Test dispatcher — routes to individual test classes based on command-line argument.

using System;

namespace VTK.Test
{
    public class Program
    {
        public static int Main(string[] args)
        {
            if (args.Length < 1)
            {
                Console.Error.WriteLine("Usage: VTK.CSharp.Tests <TestName>");
                Console.Error.WriteLine("Available tests: CSharpDelete, CSharpGCAndDelete, CSharpConcurrencyGC, CSharpBindingCoverage, CSharpRegression");
                return 1;
            }

            string testName = args[0];
            string[] testArgs = args.Length > 1 ? args[1..] : Array.Empty<string>();

            return testName switch
            {
                "CSharpDelete" => CSharpDelete.Run(testArgs),
                "CSharpGCAndDelete" => CSharpGCAndDelete.Run(testArgs),
                "CSharpConcurrencyGC" => CSharpConcurrencyGC.Run(testArgs),
                "CSharpBindingCoverage" => CSharpBindingCoverage.Run(testArgs),
                "CSharpRegression" => CSharpRegression.Run(testArgs),
                _ => Error($"Unknown test: {testName}")
            };
        }

        private static int Error(string msg)
        {
            Console.Error.WriteLine(msg);
            return 1;
        }
    }
}
