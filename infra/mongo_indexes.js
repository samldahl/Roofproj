// Run once against the target DB: mongosh "$MONGO_URI" infra/mongo_indexes.js
db.permits.createIndex({ city_id: 1, permit_number: 1 }, { unique: true });
db.permits.createIndex({ location: "2dsphere" });
db.permits.createIndex({ issue_date: -1 });
db.permits.createIndex({ city_id: 1, issue_date: -1 });
db.permits.createIndex({ contractor_name: 1 });

db.cities.createIndex({ slug: 1 }, { unique: true });

db.source_files.createIndex({ sha256: 1 }, { unique: true });
db.source_files.createIndex({ city_id: 1, received_at: -1 });

db.outreach_requests.createIndex({ city_id: 1, sent_at: -1 });
db.outreach_requests.createIndex({ status: 1, follow_up_at: 1 });

db.jobs.createIndex({ status: 1, claim_at: 1 });
db.jobs.createIndex({ created_at: 1 });
