from flask import Flask, jsonify, request
from flask_cors import CORS
import sqlite3, uuid, json, os
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'rideease.db')
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

DRIVERS = {
    'Bike': {'name': 'Arun Kumar', 'rating': 4.8, 'vehicle': 'Honda Activa', 'plate': 'TN 23 AB 4102', 'eta': 4, 'distance': '0.8 km', 'phone': '+919876540101'},
    'Auto': {'name': 'Ravi Shankar', 'rating': 4.9, 'vehicle': 'Bajaj RE', 'plate': 'TN 23 AC 2208', 'eta': 6, 'distance': '1.2 km', 'phone': '+919876540102'},
    'Car': {'name': 'Karthik S', 'rating': 4.9, 'vehicle': 'Hyundai Aura', 'plate': 'TN 23 AD 6201', 'eta': 5, 'distance': '1.0 km', 'phone': '+919876540103'},
}
MODELS = [
    {'id':'hatchback','name':'Maruti Swift','category':'Hatchback','seats':4,'baseFare':120,'perKm':12,'description':'Compact and comfortable'},
    {'id':'sedan','name':'Hyundai Aura','category':'Sedan','seats':4,'baseFare':160,'perKm':15,'description':'Extra comfort for everyday rides'},
    {'id':'suv','name':'Kia Carens','category':'SUV','seats':6,'baseFare':220,'perKm':19,'description':'More space for family and luggage'},
]

def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS bookings (
            id TEXT PRIMARY KEY, pickup TEXT NOT NULL, destination TEXT NOT NULL,
            vehicles_json TEXT NOT NULL, model_json TEXT, distance_km REAL NOT NULL,
            fare_total REAL NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL
        )''')
init_db()

def row_to_booking(row):
    if not row: return None
    data = dict(row)
    data['vehicles'] = json.loads(data.pop('vehicles_json'))
    data['model'] = json.loads(data.pop('model_json')) if data.get('model_json') else None
    data['distanceKm'] = data.pop('distance_km')
    data['fareTotal'] = data.pop('fare_total')
    data['createdAt'] = data.pop('created_at')
    data['drivers'] = [{**DRIVERS[v], 'type': v} for v, qty in data['vehicles'].items() if qty > 0]
    return data

@app.get('/api/health')
def health():
    return jsonify({'status':'ok','service':'RideEase API'})

@app.get('/api/vehicles')
def vehicles():
    return jsonify([
        {'type':'Bike','label':'Bike','capacity':'1 passenger','baseFare':40,'perKm':7,'description':'Quick rides through town'},
        {'type':'Auto','label':'Auto','capacity':'3 passengers','baseFare':60,'perKm':10,'description':'Affordable everyday travel'},
        {'type':'Car','label':'Car','capacity':'4 passengers','baseFare':120,'perKm':12,'description':'Comfortable private ride'},
    ])

@app.get('/api/car-models')
def car_models():
    return jsonify(MODELS)

@app.post('/api/fare-estimate')
def fare_estimate():
    payload = request.get_json(silent=True) or {}
    vehicles = payload.get('vehicles') or {'Bike':0,'Auto':0,'Car':1}
    distance = max(1.0, min(float(payload.get('distanceKm', 8)), 300.0))
    selected_model = next((m for m in MODELS if m['id'] == payload.get('modelId')), MODELS[1])
    details, total = [], 0
    rates = {'Bike':(40,7),'Auto':(60,10),'Car':(selected_model['baseFare'],selected_model['perKm'])}
    for kind in ['Bike','Auto','Car']:
        qty = max(0, min(int(vehicles.get(kind, 0)), 5))
        if qty:
            base, per_km = rates[kind]
            fare = round((base + per_km * distance) * qty)
            details.append({'type':kind,'quantity':qty,'unitFare':round(base + per_km*distance),'subtotal':fare})
            total += fare
    return jsonify({'distanceKm':distance,'items':details,'subtotal':total,'serviceFee':round(total*0.05),'total':round(total*1.05),'model':selected_model})

@app.post('/api/bookings')
def create_booking():
    payload = request.get_json(silent=True) or {}
    pickup = str(payload.get('pickup','')).strip()
    destination = str(payload.get('destination','')).strip()
    vehicles = payload.get('vehicles') or {}
    if not pickup or not destination:
        return jsonify({'error':'Pickup and destination are required.'}), 400
    if pickup.casefold() == destination.casefold():
        return jsonify({'error':'Pickup and destination must be different.'}), 400
    cleaned = {k:max(0,min(int(vehicles.get(k,0)),5)) for k in ['Bike','Auto','Car']}
    if not any(cleaned.values()):
        return jsonify({'error':'Select at least one vehicle.'}), 400
    distance = max(1.0, min(float(payload.get('distanceKm',8)),300.0))
    model = next((m for m in MODELS if m['id'] == payload.get('modelId')), MODELS[1])
    rates = {'Bike':(40,7),'Auto':(60,10),'Car':(model['baseFare'],model['perKm'])}
    subtotal = sum(round((rates[k][0] + rates[k][1]*distance)*qty) for k,qty in cleaned.items() if qty)
    total = round(subtotal*1.05)
    booking_id = 'RE-' + uuid.uuid4().hex[:8].upper()
    created = datetime.now(timezone.utc).isoformat(timespec='seconds')
    with connect() as db:
        db.execute('INSERT INTO bookings VALUES (?,?,?,?,?,?,?,?,?)', (booking_id,pickup,destination,json.dumps(cleaned),json.dumps(model) if cleaned['Car'] else None,distance,total,'Driver assigned',created))
        row = db.execute('SELECT * FROM bookings WHERE id=?',(booking_id,)).fetchone()
    return jsonify(row_to_booking(row)), 201

@app.get('/api/bookings')
def list_bookings():
    with connect() as db:
        rows = db.execute('SELECT * FROM bookings ORDER BY created_at DESC LIMIT 100').fetchall()
    return jsonify([row_to_booking(r) for r in rows])

@app.get('/api/bookings/<booking_id>')
def get_booking(booking_id):
    with connect() as db:
        row = db.execute('SELECT * FROM bookings WHERE id=?',(booking_id,)).fetchone()
    if not row: return jsonify({'error':'Booking not found.'}), 404
    booking = row_to_booking(row)
    # Tracking values are illustrative for this local prototype.
    booking['tracking'] = {'progress': 58, 'remainingMinutes': max(2, int(booking['distanceKm']*0.8)), 'updatedAt': datetime.now(timezone.utc).isoformat(timespec='seconds')}
    return jsonify(booking)

@app.patch('/api/bookings/<booking_id>/cancel')
def cancel_booking(booking_id):
    with connect() as db:
        cur = db.execute("UPDATE bookings SET status='Cancelled' WHERE id=? AND status!='Cancelled'", (booking_id,))
        row = db.execute('SELECT * FROM bookings WHERE id=?',(booking_id,)).fetchone()
    if not row: return jsonify({'error':'Booking not found.'}), 404
    return jsonify(row_to_booking(row))

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)
