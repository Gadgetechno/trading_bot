const express = require('express');
const cors = require('cors');
const fs = require('fs').promises;
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(cors());
app.use(express.json());
app.use(express.static('.')); // Serve your HTML files

// Whitelist file path
const WHITELIST_FILE = path.join(__dirname, 'telegram_whitelist.json');

// Initialize whitelist file if it doesn't exist
async function initializeWhitelist() {
  try {
    await fs.access(WHITELIST_FILE);
  } catch (error) {
    const initialData = {
      users: [],
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString()
    };
    await fs.writeFile(WHITELIST_FILE, JSON.stringify(initialData, null, 2));
    console.log('Whitelist file created');
  }
}

// Read whitelist
async function readWhitelist() {
  try {
    const data = await fs.readFile(WHITELIST_FILE, 'utf8');
    return JSON.parse(data);
  } catch (error) {
    console.error('Error reading whitelist:', error);
    return { users: [] };
  }
}

// Write to whitelist
async function writeWhitelist(data) {
  try {
    data.updatedAt = new Date().toISOString();
    await fs.writeFile(WHITELIST_FILE, JSON.stringify(data, null, 2));
    return true;
  } catch (error) {
    console.error('Error writing whitelist:', error);
    return false;
  }
}

// API endpoint to verify user
app.post('/api/verify-user', async (req, res) => {
  try {
    const { telegramId } = req.body;
    
    if (!telegramId || !/^\d+$/.test(telegramId)) {
      return res.status(400).json({
        success: false,
        message: 'Invalid Telegram ID format'
      });
    }

    const whitelist = await readWhitelist();
    const user = whitelist.users.find(u => u.telegramId === telegramId && u.isActive);

    if (user) {
      // Update last login
      user.lastLogin = new Date().toISOString();
      await writeWhitelist(whitelist);
      
      return res.json({
        success: true,
        message: 'User verified successfully',
        user: {
          telegramId: user.telegramId,
          username: user.username,
          firstName: user.firstName,
          joinedAt: user.joinedAt
        }
      });
    } else {
      return res.status(403).json({
        success: false,
        message: 'You are not a Tanix 2.0 member. Access Denied.'
      });
    }
  } catch (error) {
    console.error('Verification error:', error);
    return res.status(500).json({
      success: false,
      message: 'Internal server error'
    });
  }
});

// API endpoint to add new user (for Telegram bot)
app.post('/api/add-user', async (req, res) => {
  try {
    const { telegramId, username, firstName, secretKey } = req.body;
    
    // Simple secret key validation (use environment variable in production)
    const expectedSecret = process.env.BOT_SECRET_KEY || 'tanix2-secret-key-2024';
    if (secretKey !== expectedSecret) {
      return res.status(401).json({
        success: false,
        message: 'Unauthorized'
      });
    }

    if (!telegramId || !/^\d+$/.test(telegramId)) {
      return res.status(400).json({
        success: false,
        message: 'Invalid Telegram ID'
      });
    }

    const whitelist = await readWhitelist();
    
    // Check if user already exists
    const existingUser = whitelist.users.find(u => u.telegramId === telegramId);
    
    if (existingUser) {
      // Reactivate if previously deactivated
      existingUser.isActive = true;
      existingUser.updatedAt = new Date().toISOString();
      existingUser.username = username || existingUser.username;
      existingUser.firstName = firstName || existingUser.firstName;
    } else {
      // Add new user
      whitelist.users.push({
        telegramId,
        username: username || '',
        firstName: firstName || '',
        joinedAt: new Date().toISOString(),
        lastLogin: null,
        isActive: true
      });
    }

    const success = await writeWhitelist(whitelist);
    
    if (success) {
      res.json({
        success: true,
        message: 'User added to whitelist successfully'
      });
    } else {
      res.status(500).json({
        success: false,
        message: 'Failed to update whitelist'
      });
    }
  } catch (error) {
    console.error('Add user error:', error);
    res.status(500).json({
      success: false,
      message: 'Internal server error'
    });
  }
});

// API endpoint to deactivate a user (for Telegram bot)
app.post('/api/remove-user', async (req, res) => {
  try {
    const { telegramId, secretKey } = req.body;
    
    // Simple secret key validation
    const expectedSecret = process.env.BOT_SECRET_KEY || 'tanix2-secret-key-2024';
    if (secretKey !== expectedSecret) {
      return res.status(401).json({ success: false, message: 'Unauthorized' });
    }

    if (!telegramId) {
      return res.status(400).json({ success: false, message: 'Invalid Telegram ID' });
    }

    const whitelist = await readWhitelist();
    const user = whitelist.users.find(u => u.telegramId === telegramId);

    if (user) {
      user.isActive = false; // Deactivate the user
      const success = await writeWhitelist(whitelist);
      if (success) {
        res.json({ success: true, message: 'User deactivated from website' });
      } else {
        res.status(500).json({ success: false, message: 'Failed to update whitelist' });
      }
    } else {
      // If user isn't found, it's still a "success" because they are not active
      res.json({ success: true, message: 'User not found, nothing to remove' });
    }
  } catch (error) {
    console.error('Remove user error:', error);
    res.status(500).json({ success: false, message: 'Internal server error' });
  }
});

// Get whitelist stats (admin endpoint)
app.get('/api/whitelist-stats', async (req, res) => {
  try {
    const whitelist = await readWhitelist();
    const activeUsers = whitelist.users.filter(u => u.isActive);
    
    res.json({
      totalUsers: whitelist.users.length,
      activeUsers: activeUsers.length,
      lastUpdated: whitelist.updatedAt
    });
  } catch (error) {
    console.error('Stats error:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

// Start server
async function startServer() {
  await initializeWhitelist();
  
  app.listen(PORT, () => {
    console.log(`Tanix 2.0 server running on port ${PORT}`);
    console.log(`Access your site at: http://localhost:${PORT}`);
    console.log(`API endpoints:`);
    console.log(`  POST /api/verify-user - Verify Telegram user`);
    console.log(`  POST /api/add-user - Add new user (for bot)`);
    console.log(`  POST /api/remove-user - Deactivate user (for bot)`);
    console.log(`  GET /api/whitelist-stats - Get whitelist statistics`);
  });
}

startServer();