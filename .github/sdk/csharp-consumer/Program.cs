using System.Reflection;
using System.Text.Json;

if (args.Length is < 1 or > 2 || (args.Length == 2 && args[1] != "--require-onnx"))
{
    Console.Error.WriteLine("Usage: CSharpRuntimeConsumer <managed-assembly> [--require-onnx]");
    return 2;
}

try
{
    var assembly = Assembly.LoadFrom(Path.GetFullPath(args[0]));
    var initializer = assembly.GetType("VTK.VtkNativeLibrary", throwOnError: true)!;
    initializer.GetMethod("Initialize", BindingFlags.Static | BindingFlags.Public)!.Invoke(null, null);
    var names = new List<string> { "vtkPoints", "vtkImageData", "vtkBufferedArchiver", "vtkFFMPEGWriter" };
    if (args.Length == 2)
        names.Add("vtkONNXInference");
    var checkedClasses = new List<string>();
    foreach (var name in names)
    {
        var type = assembly.GetType("VTK." + name, throwOnError: true)!;
        var instance = Activator.CreateInstance(type)
            ?? throw new InvalidOperationException("Constructor returned no instance: " + name);
        try
        {
            var getter = type.GetMethod("GetClassName", BindingFlags.Instance | BindingFlags.Public,
                binder: null, types: Type.EmptyTypes, modifiers: null)
                ?? throw new MissingMethodException(name, "GetClassName");
            var className = getter.Invoke(instance, null) as string;
            if (className != name)
                throw new InvalidOperationException($"Unexpected native class for {name}: {className}");
            if (name is "vtkPoints" or "vtkImageData")
            {
                var points = type.GetMethod("GetNumberOfPoints", BindingFlags.Instance | BindingFlags.Public,
                    binder: null, types: Type.EmptyTypes, modifiers: null)
                    ?? throw new MissingMethodException(name, "GetNumberOfPoints");
                if (Convert.ToInt64(points.Invoke(instance, null)) != 0)
                    throw new InvalidOperationException("Unexpected initial point count: " + name);
            }
            checkedClasses.Add(className);
        }
        finally
        {
            ((IDisposable)instance).Dispose();
        }
    }
    Console.WriteLine(JsonSerializer.Serialize(new { outcome = "passed", classes = checkedClasses }));
    return 0;
}
catch (Exception error)
{
    Console.Error.WriteLine(error);
    return 1;
}
