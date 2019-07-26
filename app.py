#!/usr/bin/env python3

from aws_cdk import core

from weather_app.weather_app_stack import WeatherAppStack


app = core.App()
WeatherAppStack(app, "weather-app")

app.synth()
