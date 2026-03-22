# tracker-backend
lives on the raspberry pi

**I ran this to make venv**
```
python -m venv venv
source venv/bin/activate
```
**then installed the requirements**
`pip install -r requirements.txt`

**Project description**
This is a project that starts at the hardware level. It is connected through a raspberry pi that listens to signals from a button to determine whether or not I am clocked in. The frontend is live to everything going on in the pi so I am using a websocket. The hardware handlers are on the pi, obviously but so is the backend. My frontend is currently on my computer but connected through the network. Every time I press the button my LED turns on and so does an indicator light on my front end. Every time I press the toggle on the front end the LED on my hardware turns off. The updates for everything are live. I can see the counter on the UI incrementing live and as soon as I stop it, it turns off and updates my list of sessions. The main source of truth lives in the backend. So, if something wants to change anything that change is transmitted to the backend.