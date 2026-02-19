// SPDX-FileCopyrightText: Copyright (c) Ken Martin, Will Schroeder, Bill Lorensen
// SPDX-License-Identifier: BSD-3-Clause

using System;
using System.Threading;

namespace VTK
{
    public class VtkGarbageCollector : IDisposable
    {
        private Timer timer;
        private bool running;
        private bool debug;
        private TimeSpan period = TimeSpan.FromSeconds(1);
        private VtkReferenceInformation lastResult;
        private bool disposed;

        public void Start()
        {
            if (running)
            {
                return;
            }
            running = true;
            timer = new Timer(OnTimer, null, period, period);
        }

        public void Stop()
        {
            if (!running)
            {
                return;
            }
            running = false;
            timer?.Dispose();
            timer = null;
        }

        public void SetScheduleTime(TimeSpan interval)
        {
            period = interval;
            if (running)
            {
                Stop();
                Start();
            }
        }

        public bool Debug
        {
            get => debug;
            set => debug = value;
        }

        public VtkReferenceInformation LastResult => lastResult;

        public VtkReferenceInformation CollectNow()
        {
            var info = vtkObjectBase.OBJECT_MANAGER.CollectGarbage(debug);
            lastResult = info;
            if (debug)
            {
                Console.WriteLine(info);
            }
            return info;
        }

        private void OnTimer(object state)
        {
            CollectNow();
        }

        public void Dispose()
        {
            if (!disposed)
            {
                Stop();
                disposed = true;
            }
        }
    }
}
