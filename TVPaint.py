import os
import subprocess
import time
import _winreg
from System import *
from System.IO import *

from Deadline.Plugins import *
from Deadline.Scripting import *

def GetDeadlinePlugin():
    return TVPaintPlugin()

def CleanupDeadlinePlugin( deadlinePlugin ):
    deadlinePlugin.Cleanup()

class TVPaintPlugin(DeadlinePlugin):
    frameCount=0
    finishedFrameCount=0

    def __init__( self ):
        self.InitializeProcessCallback += self.InitializeProcess
        self.RenderExecutableCallback += self.RenderExecutable
        self.RenderArgumentCallback += self.RenderArgument

    def Cleanup(self):
        for stdoutHandler in self.StdoutHandlers:
            del stdoutHandler.HandleCallback

        del self.InitializeProcessCallback
        del self.RenderExecutableCallback
        del self.RenderArgumentCallback

    def InitializeProcess(self):
        self.SingleFramesOnly = False
        self.StdoutHandling = True

        #Std out handlers
        self.AddStdoutHandlerCallback(r"Frame [0-9]+ \(([0-9]+)/([0-9]+)\).*").HandleCallback += self.HandleProgress
        self.AddStdoutHandlerCallback(r"Unrecognized argument:.*").HandleCallback += self.HandleError

        # closing existing TV Paint process
        while ProcessUtils.IsProcessRunning('TVPaint Animation 11 Pro (64bits)'):
            saveScript = Path.Combine(self.GetPluginDirectory(), "SaveQuit.grg")
            cmd = '"%s" "script=%s"' % (self.RenderExecutable(), saveScript)
            subprocess.Popen(cmd)
            time.sleep(1)

        # modify registry settings, to disable windows error reporting
        path = r'SOFTWARE\Microsoft\Windows\Windows Error Reporting'
        hKey = _winreg.OpenKey(_winreg.HKEY_CURRENT_USER, path, 0,
                               _winreg.KEY_ALL_ACCESS)
        _winreg.SetValueEx(hKey, 'Disabled', 0, _winreg.REG_DWORD, 1)
        _winreg.SetValueEx(hKey, 'DontShowUI', 0, _winreg.REG_DWORD, 1)

        # ensuring scene file is accessible
        sceneFile = self.GetPluginInfoEntryWithDefault("SceneFile", "").strip()
        if not os.path.exists(sceneFile):
            raise Exception("Can't find the scene file: %s" % sceneFile)

    def RenderExecutable(self):
        versionStr = self.GetPluginInfoEntryWithDefault( "Version", "11" )

        renderExecutableList = self.GetConfigEntry( "RenderExecutable" + versionStr )

        executable = ""
        build = self.GetPluginInfoEntryWithDefault( "Build", "None" ).lower()

        if(SystemUtils.IsRunningOnWindows()):
            if( build == "32bit" ):
                self.LogInfo( "Enforcing 32 bit build of TVPaint" )
                executable = FileUtils.SearchFileListFor32Bit( renderExecutableList )
                if( executable == "" ):
                    self.LogWarning( "No 32 bit TVPaint " + versionStr + " render executable found in the semicolon separated list \"" + renderExecutableList + "\". Checking for any executable that exists instead." )

            elif( build == "64bit" ):
                self.LogInfo( "Enforcing 64 bit build of TVPaint" )
                executable = FileUtils.SearchFileListFor64Bit( renderExecutableList )
                if( executable == "" ):
                    self.LogWarning( "No 64 bit TVPaint " + versionStr + " render executable found in the semicolon separated list \"" + renderExecutableList + "\". Checking for any executable that exists instead." )

        if(executable == "" ):
            self.LogInfo( "Not enforcing a build of TVPaint" )
            executable = FileUtils.SearchFileList( renderExecutableList )
            if( executable == "" ):
                self.FailRender( "No TVPaint " + versionStr + " render executable found in the semicolon separated list \"" + renderExecutableList + "\". The path to the render executable can be configured from the Plugin Configuration in the Deadline Monitor." )
        self.LogInfo( "Rendering with executable: %s" % executable)

        return executable

    def RenderArgument(self):
        version = self.GetFloatPluginInfoEntryWithDefault( "Version", 11 )
        configFilenames = self.GetAuxiliaryFilenames()
        sceneSubmitted = False

        # Set the scene file option
        sceneFile = self.GetPluginInfoEntryWithDefault( "SceneFile", "" ).strip()

        if len(sceneFile) == 0:
            sceneFile = configFilenames[0]
            sceneSubmitted = True

        sceneFile = RepositoryUtils.CheckPathMapping( sceneFile )
        sceneFile = PathUtils.ToPlatformIndependentPath( sceneFile )

        # Supported formats: avi, bmp, cin, dip, dpx, fli, gif, iff, jpg, pcx, png, psd, rgb, pic, ras, tga, vpb
        format = self.GetPluginInfoEntryWithDefault( "OutputFormat", "JPEG" )

        # set format to upper case.
        format = format.upper()

        if format == "QUICKTIME":
            self.LogWarning("The export format '.mov(Quicktime)' is only available for 32bits version of TVPaint Animation")

        # If no output specified, it is automatically saved to the same location as the scene file.
        outputFile = self.GetPluginInfoEntryWithDefault( "OutputFile", "" ).strip()
        if len(outputFile) > 0:
            outputFile = RepositoryUtils.CheckPathMapping( outputFile )
            outputFile = PathUtils.ToPlatformIndependentPath( outputFile )

        else:
            #Fail if the scene was submitted, without the output file being submitted.
            if sceneSubmitted:
                self.FailRender( "The scene file was submitted with the job, but no output file was specified. This would result in the rendered images being lost." )

        # Specify the frame range.
        startFrame = str(self.GetStartFrame())
        endFrame = str(self.GetEndFrame())

        #Get TVPaint renderScript and initialize variables
        renderScript = Path.Combine(self.GetPluginDirectory(), "GeorgeScript.grg")
        jobMode = self.GetPluginInfoEntryWithDefault( "JobModeBox", "" )
        useCamera = self.GetBooleanPluginInfoEntry("UseCameraBox")
        alphaSaveMode = self.GetPluginInfoEntryWithDefault( "AlphaSaveModeBox", "NoPreMultiply" )
        layerName = self.GetPluginInfoEntryWithDefault( "LayerName", "" )


        #Send arguments that will be needed in Deadline's GeorgeScript to TVPaint
        initCommands = """\"cmd=tv_WriteUserString DeadlineConfig JobMode {}\"
                       \"cmd=tv_WriteUserString DeadlineConfig AlphaSaveMode {}\"
                       \"cmd=tv_WriteUserString DeadlineConfig ScenePath {}\"
                       \"cmd=tv_WriteUserString DeadlineConfig UseCamera {}\"
                       \"cmd=tv_WriteUserString DeadlineConfig ExportFormat {}\"
                       \"cmd=tv_WriteUserString DeadlineConfig StartFrame {}\"
                       \"cmd=tv_WriteUserString DeadlineConfig EndFrame {}\"
                       \"cmd=tv_WriteUserString DeadlineConfig LayerName {}\"
                       \"cmd=tv_WriteUserString DeadlineConfig ExportPath {}\" \n\n""".format(jobMode, alphaSaveMode, sceneFile, useCamera, format, startFrame, endFrame, layerName, outputFile)

        commands = ""
        if not self.GetPluginInfoEntryWithDefault( "JobModeBox", "" ) == "Script Job":
            commands = "\"script={}\"".format(renderScript)
        else:
            #Set the script file option
            customScript = self.GetPluginInfoEntryWithDefault( "ScriptFile", "" ).strip()

            if len(customScript) == 0:
                customScript = configFilenames[1]
            customScript = RepositoryUtils.CheckPathMapping( customScript )
            customScript = PathUtils.ToPlatformIndependentPath( customScript )

            commands = "\"script={}\" \"script={}\"".format(renderScript, customScript)

        arguments = initCommands+" "+commands+" "

        arguments += "\"cmd=tv_Quit\""

        return arguments


    def HandleProgress(self):
        self.SetStatusMessage( self.GetRegexMatch(0) )

        currFrame = float(self.GetRegexMatch(1))
        totalFrames = float(self.GetRegexMatch(2))
        progress = (currFrame * 100) / totalFrames
        if progress > 100:
            progress = 100
        self.SetProgress( (currFrame * 100) / totalFrames )

    def HandleError(self):
        self.FailRender( self.GetRegexMatch(0))
