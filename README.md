JETRACER-robot-car
AI-powered JetRacer robot car platform built on NVIDIA Jetson Nano, designed for autonomous driving, remote control, real-time camera streaming, and intelligent assisted driving systems.

📌 Overview
JETRACER-robot-car is a modular robotics project focused on building a smart autonomous vehicle using:


NVIDIA Jetson Nano


Python backend services


Real-time camera processing


Assisted driving logic


Remote control architecture


AI / Computer Vision integration


The project is structured for scalability and future integration with:


YOLO object detection


Lane following


ROS / ROS2


Web dashboard


Autonomous navigation


Mobile control applications



🚗 Features


🎥 Real-time camera streaming


🧠 Assisted driving system


⚡ FastAPI backend architecture


🔌 Modular hardware control


📡 Remote vehicle communication


🛣 Foundation for autonomous driving


🧩 Clean and expandable project structure


🤖 Ready for AI & Computer Vision integration



🛠 Hardware Requirements
Main Components


NVIDIA Jetson Nano


JetRacer chassis


CSI / USB Camera


Motor Driver


Servo Steering


Li-ion Battery Pack


Optional


OLED Display


Ultrasonic Sensor


IMU Sensor


GPS Module


LiDAR



💻 Software Stack
TechnologyPurposePythonMain programming languageFastAPIBackend API serverOpenCVComputer vision processingNVIDIA JetPackJetson SDKTensorRTAI accelerationPyTorchDeep learning inference

📂 Project Structure
JETRACER-robot-car/│├── docs/│   └── protocol_v1.md│├── host_control/│   └── backend/│       └── app/│           ├── __init__.py│           ├── assisted_driver.py│           ├── camera.py│           ├── config.py│├── .gitignore└── README.md

⚙️ Installation
1. Clone Repository
git clone https://github.com/chanhuynguyen-ai/JETRACER-robot-car.gitcd JETRACER-robot-car

2. Create Python Environment
python3 -m venv venvsource venv/bin/activate

3. Install Dependencies
pip install -r requirements.txt

▶️ Running the Project
Start Backend Server
uvicorn host_control.backend.app.main:app --host 0.0.0.0 --port 8000

🌐 API Access
After starting the server:
http://<JETSON_IP>:8000
Swagger API documentation:
http://<JETSON_IP>:8000/docs

🧠 Future Development
Planned features:


 YOLOv8 object detection


 Autonomous lane following


 WebSocket low-latency control


 ROS2 integration


 Mobile app controller


 GPS navigation


 SLAM mapping


 Multi-camera system


 Cloud telemetry



📡 Communication Architecture
Controller Device        │        ▼ FastAPI Backend Server        │ ┌──────┴──────┐ ▼             ▼Camera     Motor Control ▼             ▼AI Vision   Steering System

🔒 Safety Notes


Always test the vehicle in a safe environment.


Use low throttle values during development.


Monitor Jetson Nano temperature during AI inference.


Ensure stable battery voltage before operation.



📷 Demo
Add demo images or videos here
![demo](docs/demo.png)

🤝 Contributing
Contributions are welcome.


Fork the repository


Create a feature branch


Commit changes


Push to your branch


Open a Pull Request



📄 License
This project is licensed under the MIT License.

👨‍💻 Author
Huy Nguyen
GitHub:
https://github.com/chanhuynguyen-ai

⭐ Support
If you find this project useful, consider giving it a star on GitHub.
