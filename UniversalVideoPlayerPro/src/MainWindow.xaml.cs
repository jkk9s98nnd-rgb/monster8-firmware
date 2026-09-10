using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Windows.ApplicationModel.DataTransfer;
using Windows.Media.Core;
using Windows.Media.Playback;
using Windows.Storage;
using Windows.Storage.Pickers;
using Windows.Storage.Streams;
using Windows.System;
using WinRT.Interop;

namespace UniversalVideoPlayerPro;

public sealed partial class MainWindow : Window
{
    private readonly MediaPlayer _mediaPlayer = new();
    private readonly List<IRandomAccessStream> _subtitleStreams = new();
    private MediaSource? _mediaSource;
    private MediaPlaybackItem? _playbackItem;
    private AppWindow? _appWindow;
    private bool _updatingSeek;
    private bool _isFullScreen;

    private static readonly string[] MediaExtensions =
    {
        ".mp4", ".m4v", ".mkv", ".mov", ".avi", ".wmv", ".webm",
        ".mpg", ".mpeg", ".mpe", ".mts", ".m2ts", ".ts", ".3gp",
        ".3g2", ".asf", ".hevc", ".h265", ".265", ".m2v", ".vob"
    };

    private static readonly HashSet<string> DirectHevcExtensions = new(StringComparer.OrdinalIgnoreCase)
    {
        ".hevc", ".h265", ".265"
    };

    public MainWindow()
    {
        InitializeComponent();
        ConfigureWindow();
        TryApplyMica();

        Player.SetMediaPlayer(_mediaPlayer);
        _mediaPlayer.Volume = 0.80;
        _mediaPlayer.MediaOpened += MediaPlayer_MediaOpened;
        _mediaPlayer.MediaFailed += MediaPlayer_MediaFailed;
        _mediaPlayer.PlaybackSession.PositionChanged += PlaybackSession_PositionChanged;
        _mediaPlayer.PlaybackSession.NaturalDurationChanged += PlaybackSession_NaturalDurationChanged;
        _mediaPlayer.PlaybackSession.PlaybackStateChanged += PlaybackSession_PlaybackStateChanged;
        Closed += MainWindow_Closed;
    }

    private void ConfigureWindow()
    {
        var hwnd = WindowNative.GetWindowHandle(this);
        var windowId = Microsoft.UI.Win32Interop.GetWindowIdFromWindow(hwnd);
        _appWindow = AppWindow.GetFromWindowId(windowId);
        _appWindow.Resize(new Windows.Graphics.SizeInt32(1280, 760));
    }

    private void TryApplyMica()
    {
        try { SystemBackdrop = new MicaBackdrop(); }
        catch { }
    }

    private FileOpenPicker CreateVideoPicker()
    {
        var picker = new FileOpenPicker { SuggestedStartLocation = PickerLocationId.VideosLibrary, ViewMode = PickerViewMode.Thumbnail };
        foreach (var extension in MediaExtensions) picker.FileTypeFilter.Add(extension);
        InitializeWithWindow.Initialize(picker, WindowNative.GetWindowHandle(this));
        return picker;
    }

    private FileOpenPicker CreateSubtitlePicker()
    {
        var picker = new FileOpenPicker { SuggestedStartLocation = PickerLocationId.VideosLibrary, ViewMode = PickerViewMode.List };
        picker.FileTypeFilter.Add(".srt");
        picker.FileTypeFilter.Add(".vtt");
        picker.FileTypeFilter.Add(".ttml");
        InitializeWithWindow.Initialize(picker, WindowNative.GetWindowHandle(this));
        return picker;
    }

    private async void OpenButton_Click(object sender, RoutedEventArgs e)
    {
        var file = await CreateVideoPicker().PickSingleFileAsync();
        if (file != null) await OpenMediaAsync(file);
    }

    private async Task OpenMediaAsync(StorageFile file)
    {
        FileNameText.Text = file.Name;
        StatusInfoBar.IsOpen = false;
        var extension = Path.GetExtension(file.Name);
        if (DirectHevcExtensions.Contains(extension) && !await HasHevcDecoderAsync())
        {
            await ShowHevcRequiredDialogAsync();
            return;
        }

        DisposeCurrentMedia();
        _mediaSource = MediaSource.CreateFromStorageFile(file);
        _playbackItem = new MediaPlaybackItem(_mediaSource);
        _mediaPlayer.Source = _playbackItem;
        EmptyState.Visibility = Visibility.Collapsed;
        _mediaPlayer.Play();
    }

    private void PlayPauseButton_Click(object sender, RoutedEventArgs e)
    {
        if (_mediaPlayer.Source == null) return;
        if (_mediaPlayer.PlaybackSession.PlaybackState == MediaPlaybackState.Playing) _mediaPlayer.Pause();
        else _mediaPlayer.Play();
    }

    private void StopButton_Click(object sender, RoutedEventArgs e)
    {
        if (_mediaPlayer.Source == null) return;
        _mediaPlayer.Pause();
        _mediaPlayer.PlaybackSession.Position = TimeSpan.Zero;
    }

    private void Back10Button_Click(object sender, RoutedEventArgs e) => SeekRelative(-10);
    private void Forward10Button_Click(object sender, RoutedEventArgs e) => SeekRelative(10);

    private void SeekRelative(double seconds)
    {
        if (_mediaPlayer.Source == null) return;
        var session = _mediaPlayer.PlaybackSession;
        var target = session.Position + TimeSpan.FromSeconds(seconds);
        if (target < TimeSpan.Zero) target = TimeSpan.Zero;
        if (session.NaturalDuration > TimeSpan.Zero && target > session.NaturalDuration) target = session.NaturalDuration;
        session.Position = target;
    }

    private void SeekSlider_ValueChanged(object sender, Microsoft.UI.Xaml.Controls.Primitives.RangeBaseValueChangedEventArgs e)
    {
        if (_updatingSeek || _mediaPlayer.Source == null) return;
        _mediaPlayer.PlaybackSession.Position = TimeSpan.FromSeconds(e.NewValue);
    }

    private void VolumeSlider_ValueChanged(object sender, Microsoft.UI.Xaml.Controls.Primitives.RangeBaseValueChangedEventArgs e)
    {
        _mediaPlayer.Volume = Math.Clamp(e.NewValue / 100.0, 0, 1);
    }

    private void SpeedComboBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (SpeedComboBox.SelectedItem is ComboBoxItem item &&
            double.TryParse(item.Tag?.ToString(), System.Globalization.NumberStyles.Float,
                System.Globalization.CultureInfo.InvariantCulture, out var rate))
            _mediaPlayer.PlaybackSession.PlaybackRate = rate;
    }

    private async void SubtitleButton_Click(object sender, RoutedEventArgs e)
    {
        if (_mediaSource == null)
        {
            ShowInfo("Open a video first.", InfoBarSeverity.Informational);
            return;
        }
        var file = await CreateSubtitlePicker().PickSingleFileAsync();
        if (file == null) return;
        try
        {
            var stream = await file.OpenReadAsync();
            _subtitleStreams.Add(stream);
            _mediaSource.ExternalTimedTextSources.Add(TimedTextSource.CreateFromStream(stream));
            ShowInfo($"Subtitle loaded: {file.Name}", InfoBarSeverity.Success);
        }
        catch (Exception ex) { ShowInfo($"Could not load subtitle: {ex.Message}", InfoBarSeverity.Error); }
    }

    private void FullScreenButton_Click(object sender, RoutedEventArgs e)
    {
        if (_appWindow == null) return;
        _isFullScreen = !_isFullScreen;
        _appWindow.SetPresenter(_isFullScreen ? AppWindowPresenterKind.FullScreen : AppWindowPresenterKind.Default);
        FullScreenButton.Content = _isFullScreen ? "Exit full screen" : "Full screen";
    }

    private async void HevcButton_Click(object sender, RoutedEventArgs e)
    {
        if (await HasHevcDecoderAsync()) ShowInfo("HEVC/H.265 playback support is installed on this PC.", InfoBarSeverity.Success);
        else await ShowHevcRequiredDialogAsync();
    }

    private static async Task<bool> HasHevcDecoderAsync()
    {
        try
        {
            var codecs = await new CodecQuery().FindAllAsync(CodecKind.Video, CodecCategory.Decoder, CodecSubtypes.VideoFormatHevc);
            return codecs.Count > 0;
        }
        catch { return false; }
    }

    private async Task ShowHevcRequiredDialogAsync()
    {
        var dialog = new ContentDialog
        {
            XamlRoot = RootGrid.XamlRoot,
            Title = "HEVC support required",
            Content = "This video uses HEVC/H.265. Install Microsoft's HEVC Video Extensions to play HEVC video in Universal Video Player Pro.",
            PrimaryButtonText = "Install HEVC support",
            CloseButtonText = "Cancel",
            DefaultButton = ContentDialogButton.Primary
        };
        if (await dialog.ShowAsync() == ContentDialogResult.Primary)
            await Launcher.LaunchUriAsync(new Uri("ms-windows-store://pdp/?ProductId=9NMZLZ57R3T7"));
    }

    private void MediaPlayer_MediaOpened(MediaPlayer sender, object args)
    {
        DispatcherQueue.TryEnqueue(() =>
        {
            EmptyState.Visibility = Visibility.Collapsed;
            DurationText.Text = FormatTime(sender.PlaybackSession.NaturalDuration);
            SeekSlider.Maximum = Math.Max(1, sender.PlaybackSession.NaturalDuration.TotalSeconds);
        });
    }

    private void MediaPlayer_MediaFailed(MediaPlayer sender, MediaPlayerFailedEventArgs args)
    {
        DispatcherQueue.TryEnqueue(async () =>
        {
            if (!await HasHevcDecoderAsync()) await ShowHevcRequiredDialogAsync();
            else ShowInfo($"Playback error: {args.ErrorMessage}", InfoBarSeverity.Error);
        });
    }

    private void PlaybackSession_PositionChanged(MediaPlaybackSession sender, object args)
    {
        DispatcherQueue.TryEnqueue(() =>
        {
            _updatingSeek = true;
            SeekSlider.Value = Math.Min(SeekSlider.Maximum, Math.Max(0, sender.Position.TotalSeconds));
            CurrentTimeText.Text = FormatTime(sender.Position);
            _updatingSeek = false;
        });
    }

    private void PlaybackSession_NaturalDurationChanged(MediaPlaybackSession sender, object args)
    {
        DispatcherQueue.TryEnqueue(() =>
        {
            SeekSlider.Maximum = Math.Max(1, sender.NaturalDuration.TotalSeconds);
            DurationText.Text = FormatTime(sender.NaturalDuration);
        });
    }

    private void PlaybackSession_PlaybackStateChanged(MediaPlaybackSession sender, object args)
    {
        DispatcherQueue.TryEnqueue(() => PlayPauseButton.Content = sender.PlaybackState == MediaPlaybackState.Playing ? "Ⅱ" : "▶");
    }

    private void RootGrid_DragOver(object sender, DragEventArgs e)
    {
        if (!e.DataView.Contains(StandardDataFormats.StorageItems)) return;
        e.AcceptedOperation = DataPackageOperation.Copy;
        e.DragUIOverride.Caption = "Play video";
        e.DragUIOverride.IsCaptionVisible = true;
    }

    private async void RootGrid_Drop(object sender, DragEventArgs e)
    {
        if (!e.DataView.Contains(StandardDataFormats.StorageItems)) return;
        var items = await e.DataView.GetStorageItemsAsync();
        var file = items.OfType<StorageFile>().FirstOrDefault(f => MediaExtensions.Contains(Path.GetExtension(f.Name), StringComparer.OrdinalIgnoreCase));
        if (file != null) await OpenMediaAsync(file);
    }

    private void ShowInfo(string message, InfoBarSeverity severity)
    {
        StatusInfoBar.Message = message;
        StatusInfoBar.Severity = severity;
        StatusInfoBar.IsOpen = true;
    }

    private static string FormatTime(TimeSpan time) => time.TotalHours >= 1
        ? $"{(int)time.TotalHours:00}:{time.Minutes:00}:{time.Seconds:00}"
        : $"{time.Minutes:00}:{time.Seconds:00}";

    private void DisposeCurrentMedia()
    {
        _mediaPlayer.Pause();
        _mediaPlayer.Source = null;
        _playbackItem = null;
        _mediaSource?.Dispose();
        _mediaSource = null;
        foreach (var stream in _subtitleStreams) stream.Dispose();
        _subtitleStreams.Clear();
    }

    private void MainWindow_Closed(object sender, WindowEventArgs args)
    {
        DisposeCurrentMedia();
        _mediaPlayer.Dispose();
    }
}
