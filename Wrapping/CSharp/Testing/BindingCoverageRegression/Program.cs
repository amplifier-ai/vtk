// SPDX-FileCopyrightText: Copyright (c) Ken Martin, Will Schroeder, Bill Lorensen
// SPDX-License-Identifier: BSD-3-Clause

using System;
using System.Collections.Generic;
using System.IO;

namespace VTK.Test
{
    internal enum Failure
    {
        None,
        Constructor,
        ConstructorNativeLoad,
        NativeLoad,
        EmptyClassName,
        NullClassName,
        ClassName,
        Disposal,
        ClassNameAndDisposal,
    }

    internal static class CoverageScenario
    {
        internal static Failure Failure;
        internal static readonly List<string> DisposalAttempts = new List<string>();
    }

    internal static class Program
    {
        private static int Main()
        {
            int failures = 0;
            failures += Check(Failure.None, 0, null);
            failures += Check(Failure.Constructor, 1, "synthetic constructor failure");
            failures += Check(Failure.ConstructorNativeLoad, 1, "synthetic constructor native load failure");
            failures += Check(Failure.NativeLoad, 1, "synthetic native load failure");
            failures += Check(Failure.EmptyClassName, 1, "empty class name");
            failures += Check(Failure.NullClassName, 1, "empty class name");
            failures += Check(Failure.ClassName, 1, "synthetic class name failure");
            failures += Check(Failure.Disposal, 1, "synthetic disposal failure");
            failures += Check(Failure.ClassNameAndDisposal, 1, "synthetic class name failure");
            Console.WriteLine($"Binding coverage failure regression: {failures} failing cases.");
            return failures == 0 ? 0 : 1;
        }

        private static int Check(Failure failure, int expectedResult, string expectedDiagnostic)
        {
            CoverageScenario.Failure = failure;
            CoverageScenario.DisposalAttempts.Clear();
            var output = new StringWriter();
            var error = new StringWriter();
            TextWriter originalOutput = Console.Out;
            TextWriter originalError = Console.Error;
            int result;
            try
            {
                Console.SetOut(output);
                Console.SetError(error);
                result = CSharpBindingCoverage.Run(Array.Empty<string>());
            }
            finally
            {
                Console.SetOut(originalOutput);
                Console.SetError(originalError);
            }

            bool constructorFailed = failure == Failure.Constructor || failure == Failure.ConstructorNativeLoad;
            var expectedDisposals = new List<string> { "vtkPointsSuccess", "vtkDoubleArrayClassNameFault" };
            if (!constructorFailed)
            {
                expectedDisposals.Add("vtkIntArrayConstructorFault");
            }
            expectedDisposals.Sort(StringComparer.Ordinal);
            CoverageScenario.DisposalAttempts.Sort(StringComparer.Ordinal);
            string actualDisposals = string.Join(",", CoverageScenario.DisposalAttempts);
            string expectedDisposalNames = string.Join(",", expectedDisposals);
            bool correct = result == expectedResult
                && actualDisposals == expectedDisposalNames
                && output.ToString().Contains("Skipped: 4")
                && output.ToString().Contains($"Errors: {(failure == Failure.None ? 0 : 1)}")
                && (expectedDiagnostic == null || error.ToString().Contains(expectedDiagnostic));
            if (failure == Failure.ClassNameAndDisposal)
            {
                correct &= error.ToString().Contains("synthetic disposal failure");
            }
            Console.WriteLine($"{(correct ? "PASS" : "FAIL")}: {failure}; result={result}; disposal attempts={actualDisposals}");
            if (!correct)
            {
                Console.Error.WriteLine($"Expected result={expectedResult}, disposal attempts={expectedDisposalNames}.");
                Console.Error.Write(output.ToString());
                Console.Error.Write(error.ToString());
                return 1;
            }
            return 0;
        }
    }
}
