const http = require('http');

const API_BASE_URL = process.env.API_BASE_URL || 'http://localhost:8000';

const syntheticPRs = [
  {
    purchase_requisition_id: 'REQ_DEMO_01',
    purchasing_group: 'P01',
    created_by_user: 'JSMITH',
    requisition_date: new Date().toISOString().split('T')[0],
    items: [
      {
        purchase_requisition_item: '00010',
        material: 'MAT_LAPTOP_001',
        vendor_id: 'VEND001',
        order_quantity: 2,
        net_price_amount: 1220.0,
        purchasing_organization: '1000',
        account_assignment_category: 'K'
      }
    ]
  },
  {
    purchase_requisition_id: 'REQ_DEMO_02',
    purchasing_group: 'P02',
    created_by_user: 'ALICEW',
    requisition_date: new Date().toISOString().split('T')[0],
    items: [
      {
        purchase_requisition_item: '00010',
        material: 'MAT_LAPTOP_001',
        vendor_id: 'VEND002',
        order_quantity: 1,
        net_price_amount: 1650.0,
        purchasing_organization: '1000',
        account_assignment_category: 'K'
      }
    ]
  },
  {
    purchase_requisition_id: 'REQ_DEMO_03',
    purchasing_group: 'P01',
    created_by_user: 'BOBM',
    requisition_date: new Date().toISOString().split('T')[0],
    items: [
      {
        purchase_requisition_item: '00010',
        material: 'MAT_SERVER_004',
        vendor_id: 'VEND006',
        order_quantity: 8,
        net_price_amount: 4750.0,
        purchasing_organization: '1000',
        account_assignment_category: 'K'
      }
    ]
  }
];

async function postPR(pr) {
  return new Promise((resolve) => {
    const data = JSON.stringify(pr);
    const url = new URL(`${API_BASE_URL}/requisitions/ingest`);
    
    const req = http.request(
      url,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(data)
        }
      },
      (res) => {
        let body = '';
        res.on('data', (chunk) => (body += chunk));
        res.on('end', () => {
          if (res.statusCode >= 200 && res.statusCode < 300) {
            console.log(`[SEED PR] Successfully ingested PR ${pr.purchase_requisition_id}`);
            resolve(JSON.parse(body));
          } else {
            console.warn(`[SEED PR] Server responded with ${res.statusCode} for ${pr.purchase_requisition_id}`);
            resolve(null);
          }
        });
      }
    );
    
    req.on('error', () => {
      console.log(`[SEED PR] Note: Fast API endpoint ${API_BASE_URL} offline during seed execution. Local DB already populated via seed.py.`);
      resolve(null);
    });

    req.write(data);
    req.end();
  });
}

async function run() {
  console.log("Submitting synthetic PRs to FastAPI endpoint for LangGraph triage processing...");
  for (const pr of syntheticPRs) {
    await postPR(pr);
  }
  console.log("Synthetic PR seeding finished.");
}

run();
