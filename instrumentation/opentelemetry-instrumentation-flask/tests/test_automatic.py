# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import click
import flask
from werkzeug.test import Client
from werkzeug.wrappers import Response

from opentelemetry import trace as trace_api
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.test.wsgitestutil import WsgiTestBase
from opentelemetry.trace.status import StatusCode

# pylint: disable=import-error
from .base_test import InstrumentationTest


class TestAutomatic(InstrumentationTest, WsgiTestBase):
    def setUp(self):
        super().setUp()

        FlaskInstrumentor().instrument()

        self.app = flask.Flask(__name__)

        self._common_initialization()

    def tearDown(self):
        super().tearDown()
        with self.disable_logging():
            FlaskInstrumentor().uninstrument()

    def test_uninstrument(self):
        # pylint: disable=access-member-before-definition
        resp = self.client.get("/hello/123")
        self.assertEqual(200, resp.status_code)
        self.assertEqual([b"Hello: 123"], list(resp.response))
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 1)

        FlaskInstrumentor().uninstrument()
        self.app = flask.Flask(__name__)

        self.app.route("/hello/<int:helloid>")(self._hello_endpoint)
        # pylint: disable=attribute-defined-outside-init
        self.client = Client(self.app, Response)

        resp = self.client.get("/hello/123")
        self.assertEqual(200, resp.status_code)
        self.assertEqual([b"Hello: 123"], list(resp.response))
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 1)

    def test_exluded_urls_explicit(self):
        FlaskInstrumentor().uninstrument()
        FlaskInstrumentor().instrument(excluded_urls="/hello/456")

        self.app = flask.Flask(__name__)
        self.app.route("/hello/<int:helloid>")(self._hello_endpoint)
        client = Client(self.app, Response)

        resp = client.get("/hello/123")
        self.assertEqual(200, resp.status_code)
        self.assertEqual([b"Hello: 123"], list(resp.response))
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 1)

        resp = client.get("/hello/456")
        self.assertEqual(200, resp.status_code)
        self.assertEqual([b"Hello: 456"], list(resp.response))
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 1)

    def test_no_op_tracer_provider(self):
        FlaskInstrumentor().uninstrument()
        FlaskInstrumentor().instrument(
            tracer_provider=trace_api.NoOpTracerProvider()
        )

        self.app = flask.Flask(__name__)
        self.app.route("/hello/<int:helloid>")(self._hello_endpoint)
        # pylint: disable=attribute-defined-outside-init
        self.client = Client(self.app, Response)
        self.client.get("/hello/123")

        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 0)

    def test_cli_command_wrapping(self):
        @self.app.cli.command()
        def flask_command():
            print("flask")
            pass

        runner = self.app.test_cli_runner()
        result = runner.invoke(args=["flask-command"])
        (span,) = self.memory_exporter.get_finished_spans()

        self.assertEqual(span.status.status_code, StatusCode.UNSET)
        self.assertEqual(span.name, "flask-command")

    def test_cli_command_wrapping_with_name(self):
        @self.app.cli.command("mycommand")
        def flask_command():
            print("my")
            pass

        runner = self.app.test_cli_runner()
        result = runner.invoke(args=["mycommand"])
        (span,) = self.memory_exporter.get_finished_spans()

        self.assertEqual(span.status.status_code, StatusCode.UNSET)
        self.assertEqual(span.name, "mycommand")

    def test_cli_command_wrapping_with_options(self):
        @self.app.cli.command()
        @click.option("--option", default="default")
        def my_command_with_opts(option):
            print("opts")
            pass

        runner = self.app.test_cli_runner()
        result = runner.invoke(
            args=["my-command-with-opts", "--option", "option"],
        )
        (span,) = self.memory_exporter.get_finished_spans()

        self.assertEqual(span.status.status_code, StatusCode.UNSET)
        self.assertEqual(span.name, "my-command-with-opts")

    def test_cli_command_raises_error(self):
        @self.app.cli.command()
        def command_raises():
            print("raises")
            raise ValueError()

        runner = self.app.test_cli_runner()
        result = runner.invoke(args=["command-raises"])
        (span,) = self.memory_exporter.get_finished_spans()

        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(span.name, "command-raises")
