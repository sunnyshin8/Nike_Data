
import React from 'react';
import { Star, ShoppingBag } from 'lucide-react';

export interface Product {
    Product_URL: string;
    Product_Image_URL: string;
    Product_Tagging: string;
    Product_Name: string;
    Product_Description: string;
    Original_Price: string;
    Discount_Price: string;
    Sizes_Available: string;
    Vouchers: string;
    Available_Colors: string;
    Color_Shown: string;
    Style_Code: string;
    Rating_Score: string;
    Review_Count: string;
}

export function ProductCard({ product }: { product: Product }) {
    const price = product.Discount_Price || product.Original_Price;
    const original = product.Discount_Price ? product.Original_Price : null;

    return (
        <div className="group relative bg-white border border-gray-100 rounded-2xl hover:shadow-xl transition-all duration-300 overflow-hidden flex flex-col h-full hover:-translate-y-1">
            {/* Image Container */}
            <div className="relative aspect-[4/5] bg-gray-50 overflow-hidden">
                {product.Product_Image_URL ? (
                    <img
                        src={product.Product_Image_URL}
                        alt={product.Product_Name}
                        className="w-full h-full object-cover object-center group-hover:scale-110 transition-transform duration-700 ease-in-out"
                    />
                ) : (
                    <div className="w-full h-full flex items-center justify-center text-gray-400 bg-gray-100">No Image</div>
                )}

                {product.Product_Tagging && (
                    <div className="absolute top-3 left-3 bg-white/90 backdrop-blur-sm text-gray-900 text-xs font-bold px-3 py-1.5 rounded-full shadow-sm tracking-wide uppercase">
                        {product.Product_Tagging}
                    </div>
                )}

                {/* Quick Action Overlay */}
                <div className="absolute bottom-0 left-0 right-0 p-4 translate-y-full group-hover:translate-y-0 transition-transform duration-300 bg-gradient-to-t from-black/50 to-transparent">
                    <button className="w-full py-3 bg-white text-black font-bold text-sm uppercase tracking-wider hover:bg-gray-100 transition-colors rounded-xl">
                        Quick View
                    </button>
                </div>
            </div>

            {/* Content */}
            <div className="p-5 flex flex-col flex-grow text-left space-y-3">
                <div>
                    <h3 className="font-bold text-lg text-gray-900 line-clamp-1 group-hover:text-orange-600 transition-colors">
                        {product.Product_Name}
                    </h3>
                    <p className="text-sm text-gray-500 line-clamp-1 font-medium">{product.Product_Description}</p>
                </div>

                <div className="flex items-center gap-1.5 text-xs font-medium">
                    <div className="flex text-amber-500">
                        {[...Array(5)].map((_, i) => (
                            <Star key={i} className={`w-3.5 h-3.5 ${i < Math.floor(Number(product.Rating_Score || 0)) ? 'fill-current' : 'text-gray-300'}`} />
                        ))}
                    </div>
                    <span className="text-gray-900">{product.Rating_Score || 'N/A'}</span>
                    <span className="text-gray-400">({product.Review_Count?.replace(/[^0-9]/g, '') || 0})</span>
                </div>

                <div className="mt-auto pt-4 border-t border-gray-50 flex items-end justify-between">
                    <div className="flex flex-col">
                        {original && (
                            <span className="text-xs text-gray-400 line-through font-medium mb-0.5">{original}</span>
                        )}
                        <span className="text-xl font-bold text-gray-900 tracking-tight">{price}</span>
                    </div>
                    <a
                        href={product.Product_URL}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="p-2.5 bg-black text-white rounded-full hover:bg-orange-600 hover:text-white transition-all shadow-lg hover:shadow-orange-500/30"
                    >
                        <ShoppingBag className="w-5 h-5" />
                    </a>
                </div>
            </div>
        </div>
    );
}
