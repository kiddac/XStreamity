#!/usr/bin/python
# -*- coding: utf-8 -*-

# A Job consists of many "Tasks".
# A task is the run of an external tool, with proper methods for failure handling

from __future__ import division
from __future__ import print_function

from . import _

from Tools.CList import CList
import os
import sys
from six.moves import map
from six.moves import range

isDreambox = False
if os.path.exists("/usr/bin/apt-get"):
    isDreambox = True

pythonVer = sys.version_info.major


class Job(object):
    NOT_STARTED, IN_PROGRESS, FINISHED, FAILED = list(range(4))

    def __init__(self, name):
        self.tasks = []
        self.resident_tasks = []
        self.workspace = "/tmp"
        self.current_task = 0
        self.callback = None
        self.name = name
        self.finished = False
        self.end = 100
        self.__progress = 0
        self.weightScale = 1
        self.afterEvent = None
        self.state_changed = CList()
        self.status = self.NOT_STARTED
        self.onSuccess = None

    # description is a dict
    def fromDescription(self, description):
        pass

    def createDescription(self):
        return None

    def getProgress(self):
        if self.current_task == len(self.tasks):
            return self.end
        t = self.tasks[self.current_task]
        jobprogress = t.weighting * t.progress / float(t.end) + sum([task.weighting for task in self.tasks[:self.current_task]])
        return int(jobprogress * self.weightScale)

    progress = property(getProgress)

    def getStatustext(self):
        return {self.NOT_STARTED: _("Waiting"), self.IN_PROGRESS: _("In progress"), self.FINISHED: _("Finished"), self.FAILED: _("Failed")}[self.status]

    def task_progress_changed_CB(self):
        self.state_changed()

    def addTask(self, task):
        task.job = self
        task.task_progress_changed = self.task_progress_changed_CB
        self.tasks.append(task)

    def start(self, callback):
        assert self.callback is None
        self.callback = callback
        self.restart()

    def restart(self):
        self.status = self.IN_PROGRESS
        self.state_changed()
        self.runNext()
        sumTaskWeightings = sum([t.weighting for t in self.tasks]) or 1
        self.weightScale = self.end / float(sumTaskWeightings)

    def runNext(self):
        if self.current_task == len(self.tasks):
            if len(self.resident_tasks) == 0:
                self.status = self.FINISHED
                self.state_changed()
                self.callback(self, None, [])
                self.callback = None
            else:
                print("[Task] still waiting for %d resident task(s) %s to finish" % (len(self.resident_tasks), str(self.resident_tasks)))
        else:
            self.tasks[self.current_task].run(self.taskCallback)
            self.state_changed()

    def taskCallback(self, task, res, stay_resident=False):
        cb_idx = self.tasks.index(task)
        if stay_resident:
            if cb_idx not in self.resident_tasks:
                self.resident_tasks.append(self.current_task)
                print("[Task] going resident:", task)
            else:
                print("[Task] keeps staying resident:", task)
                return
        if len(res):
            print(">>> Error:", res)
            self.status = self.FAILED
            self.state_changed()
            self.callback(self, task, res)
        if cb_idx != self.current_task:
            if cb_idx in self.resident_tasks:
                print("[Task] resident task finished:", task)
                self.resident_tasks.remove(cb_idx)
        if not res:
            self.state_changed()
            self.current_task += 1
            self.runNext()

    def retry(self):
        assert self.status == self.FAILED
        self.restart()

    def abort(self):
        if self.current_task < len(self.tasks):
            self.tasks[self.current_task].abort()
        for i in self.resident_tasks:
            self.tasks[i].abort()

    def cancel(self):
        self.abort()

    def __str__(self):
        return "Components.Task.Job name=%s #tasks=%s" % (self.name, len(self.tasks))


class Task(object):
    def __init__(self, job, name):
        self.name = name
        self.immediate_preconditions = []
        self.global_preconditions = []
        self.postconditions = []
        self.returncode = None
        self.initial_input = None
        self.job = None
        self.end = 100
        self.weighting = 100
        self.__progress = 0
        self.cmd = None
        self.cwd = "/tmp"
        self.args = []
        self.cmdline = None
        self.task_progress_changed = None
        self.output_line = ""
        job.addTask(self)
        self.container = None

    def setCommandline(self, cmd, args):
        self.cmd = cmd
        self.args = args

    def setTool(self, tool):
        self.cmd = tool
        self.args = [tool]
        self.global_preconditions.append(ToolExistsPrecondition())
        self.postconditions.append(ReturncodePostcondition())

    def setCmdline(self, cmdline):
        self.cmdline = cmdline

    def checkPreconditions(self, immediate=False):
        not_met = []
        if immediate:
            preconditions = self.immediate_preconditions
        else:
            preconditions = self.global_preconditions
        for precondition in preconditions:
            if not precondition.check(self):
                not_met.append(precondition)
        return not_met

    def run(self, callback):
        failed_preconditions = self.checkPreconditions(True) + self.checkPreconditions(False)
        if failed_preconditions:
            print("[Task] preconditions failed")
            callback(self, failed_preconditions)
            return
        self.callback = callback
        try:
            self.prepare()
            self._run()
        except Exception as ex:
            print("[Task] exception:", ex)
            self.postconditions = [FailedPostcondition(ex)]
            self.finish()

    def _run(self):
        if (self.cmd is None) and (self.cmdline is None):
            self.finish()
            return
        from enigma import eConsoleAppContainer
        self.container = eConsoleAppContainer()

        if isDreambox:
            self.appClosed_conn = self.container.appClosed.connect(self.processFinished)
            self.stdoutAvail_conn = self.container.stdoutAvail.connect(self.processStdout)
            self.stderrAvail_conn = self.container.stderrAvail.connect(self.processStderr)

        else:
            self.container.appClosed.append(self.processFinished)
            self.container.stdoutAvail.append(self.processStdout)
            self.container.stderrAvail.append(self.processStderr)

        if self.cwd is not None:
            self.container.setCWD(self.cwd)

        if not self.cmd and self.cmdline:
            print("[Task] execute:", self.container.execute(self.cmdline), self.cmdline)
        else:
            assert self.cmd is not None
            assert len(self.args) >= 1
            print("[Task] execute:", self.container.execute(self.cmd, *self.args), ' '.join(self.args))
        if self.initial_input:
            self.writeInput(self.initial_input)

    def prepare(self):
        pass

    def cleanup(self, failed):
        pass

    def processStdout(self, data):
        self.processOutput(data)

    def processStderr(self, data):
        self.processOutput(data)

    def processOutput(self, data):
        if pythonVer == 3:
            data = str(data)
        self.output_line += data
        while True:
            i = self.output_line.find('\n')
            if i == -1:
                break
            self.processOutputLine(self.output_line[:i + 1])
            self.output_line = self.output_line[i + 1:]

    def processOutputLine(self, line):
        print("[Task %s]" % self.name, line[:-1])
        pass

    def processFinished(self, returncode):
        self.returncode = returncode
        self.finish()

    def abort(self):
        if self.container:
            self.container.kill()
        self.finish(aborted=True)

    def finish(self, aborted=False):
        self.afterRun()
        not_met = []
        if aborted:
            not_met.append(AbortedPostcondition())
        else:
            for postcondition in self.postconditions:
                if not postcondition.check(self):
                    not_met.append(postcondition)
        self.cleanup(not_met)
        self.callback(self, not_met)

    def afterRun(self):
        pass

    def writeInput(self, input):
        self.container.write(input)

    def getProgress(self):
        return self.__progress

    def setProgress(self, progress):
        if progress > self.end:
            progress = self.end
        if progress < 0:
            progress = 0
        self.__progress = progress
        if self.task_progress_changed:
            self.task_progress_changed()

    progress = property(getProgress, setProgress)

    def __str__(self):
        return "Components.Task.Task name=%s" % self.name


class JobManager:

    def __init__(self):
        self.active_jobs = []
        self.failed_jobs = []
        self.job_classes = []
        self.in_background = False
        self.visible = False
        self.active_job = None

    def AddJob(self, job, onSuccess=None, onFail=None):
        job.onSuccess = onSuccess
        if onFail is None:
            job.onFail = self.notifyFailed
        else:
            job.onFail = onFail
        self.active_jobs.append(job)
        self.kick()

    def kick(self):
        if self.active_job is None:
            if self.active_jobs:
                self.active_job = self.active_jobs.pop(0)
                self.active_job.start(self.jobDone)

    def notifyFailed(self, job, task, problems):
        import Tools.Notifications
        from Screens.MessageBox import MessageBox
        if problems[0].RECOVERABLE:
            Tools.Notifications.AddNotificationWithCallback(self.errorCB, MessageBox, _("Error: %s\nRetry?") % (problems[0].getErrorMessage(task)))
            return True
        else:
            Tools.Notifications.AddNotification(MessageBox, job.name + "\n" + _("Error") + ': %s' % (problems[0].getErrorMessage(task)), type=MessageBox.TYPE_ERROR)
            return False

    def jobDone(self, job, task, problems):
        print("job", job, "completed with", problems, "in", task)
        if problems:
            if not job.onFail(job, task, problems):
                self.errorCB(False)
        else:
            self.active_job = None
            if job.onSuccess:
                job.onSuccess(job)
            self.kick()

    # Set job.onSuccess to this function if you want to pop up the jobview when the job is done/
    def popupTaskView(self, job):
        if not self.visible:
            import Tools.Notifications
            from Screens.TaskView import JobView
            self.visible = True
            Tools.Notifications.AddNotification(JobView, job)

    def errorCB(self, answer):
        if answer:
            print("[Task] retrying job")
            self.active_job.retry()
        else:
            print("[Task] not retrying job.")
            self.failed_jobs.append(self.active_job)
            self.active_job = None
            self.kick()

    def getPendingJobs(self):
        list = []
        if self.active_job:
            list.append(self.active_job)
        list += self.active_jobs
        return list


class Condition:
    def __init__(self):
        pass

    RECOVERABLE = False

    def getErrorMessage(self, task):
        return _("An unknown error occurred!") + " (%s @ task %s)" % (self.__class__.__name__, task.__class__.__name__)


class ToolExistsPrecondition(Condition):
    def __init__(self):
        pass

    def check(self, task):
        import os
        if task.cmd[0] == '/':
            self.realpath = task.cmd
            print("[Task][ToolExistsPrecondition] WARNING: usage of absolute paths for tasks should be avoided!")
            return os.access(self.realpath, os.X_OK)
        else:
            self.realpath = task.cmd
            path = os.environ.get('PATH', '').split(os.pathsep)
            path.append(task.cwd + '/')
            absolutes = list(filter(lambda _file: os.access(_file, os.X_OK), map(lambda directory, _file=task.cmd: os.path.join(directory, _file), path)))
            if absolutes:
                self.realpath = absolutes[0]
                return True

        return False

    def getErrorMessage(self, task):
        return _("A required tool (%s) was not found.") % self.realpath


class AbortedPostcondition(Condition):
    def __init__(self):
        pass

    def getErrorMessage(self, task):
        return _("Cancelled upon user request")


class ReturncodePostcondition(Condition):
    def __init__(self):
        pass

    def check(self, task):
        return task.returncode == 0

    def getErrorMessage(self, task):
        if hasattr(task, 'log') and task.log:
            log = ''.join(task.log).strip()
            log = log.split('\n')[-3:]
            log = '\n'.join(log)
            return log
        else:
            return _("Error code") + ": %s" % task.returncode


class FailedPostcondition(Condition):
    def __init__(self, exception):
        self.exception = exception

    def getErrorMessage(self, task):
        if isinstance(self.exception, int):
            if hasattr(task, 'log'):
                log = ''.join(task.log).strip()
                log = log.split('\n')[-4:]
                log = '\n'.join(log)
                return log
            else:
                return _("Error code") + " %s" % self.exception
        return str(self.exception)

    def check(self, task):
        return (self.exception is None) or (self.exception == 0)


job_manager = JobManager()
