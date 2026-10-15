# 开发期辅助：按进程名 + 最小宽度找到窗口并截图
# 用法： pwsh -File tools/grab_window.ps1 -ProcessName python -Out shot.png -MinWidth 600
param(
    [string]$ProcessName = "python",
    [string]$Out = "shot.png",
    [int]$MinWidth = 600
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class Grab {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
  [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
  [DllImport("user32.dll")] public static extern bool RedrawWindow(IntPtr h, IntPtr rect, IntPtr region, uint flags);
  public static void WakeUp(IntPtr h) {
    if (IsIconic(h)) ShowWindow(h, 9);          // SW_RESTORE
    ShowWindow(h, 5);                            // SW_SHOW
    BringWindowToTop(h);
    SetForegroundWindow(h);
    RedrawWindow(h, IntPtr.Zero, IntPtr.Zero, 0x0001 | 0x0080 | 0x0100);   // INVALIDATE | ALLCHILDREN | UPDATENOW
  }
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  public static long Find(uint target, int minW) {
    long hit = 0;
    EnumWindows((h, l) => {
      uint pid; GetWindowThreadProcessId(h, out pid);
      if (pid == target && IsWindowVisible(h)) {
        var sb = new StringBuilder(300); GetWindowTextW(h, sb, 300);
        RECT r; GetWindowRect(h, out r);
        if (sb.Length > 0 && (r.R - r.L) >= minW) { hit = h.ToInt64(); return false; }
      }
      return true;
    }, IntPtr.Zero);
    return hit;
  }
}
"@ -Language CSharp

$procs = Get-Process -Name $ProcessName -ErrorAction SilentlyContinue
if (-not $procs) { Write-Output "NO-PROCESS $ProcessName"; exit 2 }
$found = $false
foreach ($p in $procs) {
    $hv = [Grab]::Find([uint32]$p.Id, $MinWidth)
    if ($hv -eq 0) { continue }
    $h = [IntPtr]::new([int64]$hv)
    [Grab]::WakeUp($h)
    [void][Grab]::SetWindowPos($h, [IntPtr]::Zero, 40, 40, 0, 0, 0x0001 -bor 0x0010 -bor 0x0040)
    Start-Sleep -Milliseconds 2000
    [Grab]::WakeUp($h)
    Start-Sleep -Milliseconds 800
    $r = New-Object Grab+RECT
    [void][Grab]::GetWindowRect($h, [ref]$r)
    $w = $r.R - $r.L; $ht = $r.B - $r.T
    $bmp = New-Object System.Drawing.Bitmap $w, $ht
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    if ([Grab]::GetForegroundWindow() -eq $h) {
        # 窗口确实在最前：直接截屏，拿到的一定是当前画面
        $g.CopyFromScreen($r.L, $r.T, 0, 0, $bmp.Size)
        $g.Dispose()
        $how = "screen"
    } else {
        $hdc = $g.GetHdc()
        [void][Grab]::PrintWindow($h, $hdc, 2)
        $g.ReleaseHdc($hdc)
        $g.Dispose()
        $how = "printwindow"
    }
    $bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
    Write-Output ("SHOT pid={0} {1}x{2} via={3} -> {4}" -f $p.Id, $w, $ht, $how, $Out)
    $found = $true
    break
}
if (-not $found) { Write-Output "NO-WINDOW (minWidth=$MinWidth)"; exit 3 }
