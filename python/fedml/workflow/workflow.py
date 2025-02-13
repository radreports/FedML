from collections import defaultdict, namedtuple, deque
from datetime import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from types import MappingProxyType
from toposort import toposort

from fedml.workflow.jobs import Job, JobStatus
import time

Metadata = namedtuple('Metadata', ['nodes', 'topological_order', 'graph'])
Node = namedtuple('Node', ['name', 'job'])


class Workflow:
    """
    Initialize the Workflow instance.

    Parameters:
    - loop (bool): Whether the workflow should loop continuously.
    """

    def __init__(self, name, loop: bool = False):
        self.name = name
        self._metadata = None
        self._loop = loop
        self.jobs = {}

    @property
    def metadata(self):
        return self._metadata if self._metadata else None

    @property
    def loop(self):
        return self._loop

    @metadata.setter
    def metadata(self, value):
        if not self._metadata:
            self._metadata = value
        else:
            raise ValueError("Workflow metadata cannot be modified.")

    @loop.setter
    def loop(self, value: bool):
        self._loop = value

    def add_job(self, job: Job, dependencies: Optional[List[Job]] = None):
        """
         Add a job to the workflow with optional dependencies.

         Parameters:
         - job (Job): An instance of the Job class.
         - dependencies (list): A list of Job instances that this job depends on.
         - Note that the order of the dependencies is important. The workflow will only run if it is able to resolve
         - dependencies and no cyclic dependencies exist. Workflows can be looped by setting the loop parameter to True.
         """

        if not isinstance(job, Job):
            raise TypeError("Only instances of the Job class (or its subclasses) can be added to the workflow.")

        if dependencies is None:
            dependencies = []

        if not all(isinstance(dep, Job) for dep in dependencies):
            raise TypeError("Dependencies must be instances of the Job class (or its subclasses).")

        if dependencies is None:
            dependencies = []

        if job.name in self.jobs:
            raise ValueError(f"Job {job.name} already exists in workflow.")

        self.jobs[job.name] = {'job': job, 'dependencies': dependencies}

    def run(self):
        """
        Run the workflow, executing jobs in the specified order.
        """

        self._compute_workflow_metadata()
        first_run = True
        while first_run or self.loop:
            first_run = False
            for nodes in self.metadata.topological_order:
                jobs = [node.job for node in nodes]
                self._execute_and_wait(jobs)

    def _execute_and_wait(self, jobs: List[Job]):
        """
        Execute the jobs and wait for them to complete.

        Parameters:
        - jobs (list): A list of Job instances to execute.
        """

        for job in jobs:
            job.run()

        while True:
            all_completed = True
            any_errored = False
            errored_jobs = []

            for job in jobs:
                status = job.status()
                if status != JobStatus.FINISHED:
                    all_completed = False

                    if status == JobStatus.FAILED or status == JobStatus.UNDETERMINED:
                        any_errored = True
                        errored_jobs.append(job.name)

            if all_completed:
                return True

            if any_errored:
                self._kill_jobs(jobs)
                raise ValueError(f"Following jobs errored out, hence workflow cannot be completed: {errored_jobs}."
                                 "Please check the logs for more information.")

            time.sleep(60)

    def _kill_jobs(self, jobs: List[Job]):
        """
        Kill the jobs.

        Parameters:
        - jobs (list): A list of Job instances to kill.
        """
        for job in jobs:
            job.kill()

    def _compute_workflow_metadata(self):
        if self.metadata:
            raise ValueError("Workflow metadata already exists. This is not expected. Please report this issue.")

        node_dict = dict()
        graph = defaultdict(set)

        for job_name, job_instance in self.jobs.items():
            node = node_dict.get(job_name, Node(name=job_name, job=job_instance['job']))

            for dependency in job_instance['dependencies']:
                dependency_node = node_dict.get(dependency.name, Node(name=dependency.name, job=dependency))
                graph[node].add(dependency_node)

        self.metadata = Metadata(nodes=tuple(node_dict.values()),
                                 graph=MappingProxyType(graph),
                                 topological_order=tuple(toposort(graph)))

        return self.metadata
