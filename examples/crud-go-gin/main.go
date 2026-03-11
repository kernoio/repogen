package main

import (
	"net/http"
	"os"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
)

type Item struct {
	ID          uint      `json:"id" gorm:"primaryKey;autoIncrement"`
	Name        string    `json:"name" gorm:"not null;size:255"`
	Description string    `json:"description"`
	CreatedAt   time.Time `json:"created_at"`
}

var db *gorm.DB

func main() {
	var err error
	db, err = gorm.Open(postgres.Open(os.Getenv("DATABASE_URL")), &gorm.Config{})
	if err != nil {
		panic("failed to connect to database: " + err.Error())
	}
	db.AutoMigrate(&Item{})

	r := gin.Default()

	r.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok"})
	})

	r.GET("/items", func(c *gin.Context) {
		var items []Item
		db.Find(&items)
		c.JSON(http.StatusOK, items)
	})

	r.POST("/items", func(c *gin.Context) {
		var body Item
		if err := c.ShouldBindJSON(&body); err != nil || body.Name == "" {
			c.JSON(http.StatusBadRequest, gin.H{"error": "name is required"})
			return
		}
		item := Item{Name: body.Name, Description: body.Description}
		db.Create(&item)
		c.JSON(http.StatusCreated, item)
	})

	r.GET("/items/:id", func(c *gin.Context) {
		id, _ := strconv.Atoi(c.Param("id"))
		var item Item
		if result := db.First(&item, id); result.Error != nil {
			c.JSON(http.StatusNotFound, gin.H{"error": "not found"})
			return
		}
		c.JSON(http.StatusOK, item)
	})

	r.PUT("/items/:id", func(c *gin.Context) {
		id, _ := strconv.Atoi(c.Param("id"))
		var item Item
		if result := db.First(&item, id); result.Error != nil {
			c.JSON(http.StatusNotFound, gin.H{"error": "not found"})
			return
		}
		var body Item
		c.ShouldBindJSON(&body)
		item.Name = body.Name
		item.Description = body.Description
		db.Save(&item)
		c.JSON(http.StatusOK, item)
	})

	r.DELETE("/items/:id", func(c *gin.Context) {
		id, _ := strconv.Atoi(c.Param("id"))
		var item Item
		if result := db.First(&item, id); result.Error != nil {
			c.JSON(http.StatusNotFound, gin.H{"error": "not found"})
			return
		}
		db.Delete(&item)
		c.Status(http.StatusNoContent)
	})

	r.Run(":8080")
}
